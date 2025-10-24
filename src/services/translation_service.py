"""
Translation service - refactored from translate_gpu.py with proper error handling and logging.
"""

import hashlib
import json
import logging
import math
import platform
import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import torch
from accelerate import init_empty_weights, load_checkpoint_and_dispatch
from huggingface_hub import snapshot_download
from tqdm import tqdm
from transformers import AutoConfig, AutoModelForSeq2SeqLM, AutoTokenizer

from src.config import get_settings
from src.utils.gpu import log_gpu_summary

logger = logging.getLogger(__name__)

# GPU optimization settings
torch.backends.cuda.matmul.allow_tf32 = True
torch.set_float32_matmul_precision("high")  # enables TF32 on Hopper/Ampere

# Regex patterns for markdown preservation
PLACEHOLDER_RE = re.compile(r"\[\[\[TOKEN_(\d+)\]\]\]")
FENCE_RE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_OR_IMG_RE = re.compile(r"(!?\[[^\]]*\]\([^)]+\))")  # links+images
IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


class TranslationError(Exception):
    """Custom exception for translation errors."""

    pass


class TranslationService:
    """GPU-accelerated translation service for markdown documents."""

    def __init__(self):
        self.settings = get_settings()
        self.model_env = None
        self._model_loaded = False

    def load_model(self) -> None:
        """Load the translation model and tokenizer."""
        if self._model_loaded:
            return

        logger.info(f"Loading model: {self.settings.model_name}")

        try:
            gpu_summary = log_gpu_summary(logger)

            # Download model files
            repo_dir = snapshot_download(
                repo_id=self.settings.model_name,
                revision=self.settings.model_revision,
                allow_patterns=[
                    "config.json",
                    "generation_config.json",
                    "model.safetensors.index.json",
                    "model-*.safetensors",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "sentencepiece.bpe.model",
                    "special_tokens_map.json",
                    "source.spm",
                    "target.spm",
                ],
                ignore_patterns=["pytorch_model.bin.index.json", "*.bin", "*.pt"],
            )

            # Load tokenizer and config
            tokenizer = AutoTokenizer.from_pretrained(repo_dir)
            config = AutoConfig.from_pretrained(repo_dir)

            # Initialize model with empty weights
            with init_empty_weights():
                model = AutoModelForSeq2SeqLM.from_config(config)
            model.tie_weights()

            # Setup device and dtype
            device_map = {"": "cuda"} if torch.cuda.is_available() else {"": "cpu"}
            if torch.cuda.is_available():
                dtype = torch.float16
                try:
                    devices = gpu_summary.get("devices", []) if gpu_summary else []
                    if any(
                        dev.get("compute_capability", "").startswith("9")
                        or "GH200" in dev.get("name", "")
                        for dev in devices
                    ):
                        dtype = torch.bfloat16
                except Exception:
                    dtype = torch.bfloat16
            else:
                dtype = torch.float32

            # Load checkpoint and dispatch to device
            model = load_checkpoint_and_dispatch(
                model, checkpoint=repo_dir, device_map=device_map, dtype=dtype
            ).eval()

            # Language setup
            if "nllb" in self.settings.model_name:
                src_lang, tgt_lang = "eng_Latn", "fra_Latn"
                if hasattr(tokenizer, "src_lang"):
                    tokenizer.src_lang = src_lang
                forced_bos_id = getattr(tokenizer, "lang_code_to_id", {}).get(
                    tgt_lang, tokenizer.convert_tokens_to_ids(tgt_lang)
                )
            elif "mbart" in self.settings.model_name:
                src_lang, tgt_lang = "en_XX", "fr_XX"
                if hasattr(tokenizer, "src_lang"):
                    tokenizer.src_lang = src_lang
                forced_bos_id = tokenizer.lang_code_to_id[tgt_lang]
            else:
                raise TranslationError(
                    "Unsupported model; use mBART-50 or NLLB-200 variants."
                )

            # Remove legacy flags
            try:
                if hasattr(model.generation_config, "early_stopping"):
                    delattr(model.generation_config, "early_stopping")
            except Exception:
                pass

            self.model_env = {
                "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
                "dtype": dtype,
                "tokenizer": tokenizer,
                "model": model,
                "src": src_lang,
                "tgt": tgt_lang,
                "forced_bos_id": forced_bos_id,
                "model_name": self.settings.model_name,
            }

            self._model_loaded = True
            device_str = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                f"Model loaded successfully on {device_str} | Arch: {platform.machine()} | dtype: {dtype}"
            )

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise TranslationError(f"Model loading failed: {e}")

    def unload_model(self) -> None:
        """Unload the model to free memory."""
        if self.model_env:
            del self.model_env
            self.model_env = None
            self._model_loaded = False
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Model unloaded")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if not self._model_loaded:
            raise TranslationError("Model not loaded")

        tokenizer = self.model_env["tokenizer"]
        return len(
            tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]
        )

    def chunk_by_tokens(self, text: str, max_tokens: int = None) -> List[str]:
        """Split text into chunks by token count."""
        if max_tokens is None:
            max_tokens = self.settings.max_input_tokens

        if not self._model_loaded:
            raise TranslationError("Model not loaded")

        tokenizer = self.model_env["tokenizer"]

        # Simple sentence split
        sents = re.split(r"(?<=[\.\?!])\s+", text)
        chunks, buf, buf_tokens = [], [], 0

        for s in sents:
            t = self.count_tokens(s)
            if t > max_tokens:
                # Hard split long "sentence" by words
                words = s.split()
                cur = []
                for w in words:
                    candidate = " ".join(cur + [w])
                    tw = self.count_tokens(candidate)
                    if tw > max_tokens and cur:
                        chunks.append(" ".join(cur))
                        cur = [w]
                    else:
                        cur.append(w)
                if cur:
                    chunks.append(" ".join(cur))
                continue

            if buf_tokens + t <= max_tokens:
                buf.append(s)
                buf_tokens += t
            else:
                if buf:
                    chunks.append(" ".join(buf))
                buf, buf_tokens = [s], t

        if buf:
            chunks.append(" ".join(buf))

        return chunks

    def pack_by_token_budget(
        self, pieces: List[str], max_tokens_per_batch: int
    ) -> List[List[str]]:
        """Pack text pieces into batches by token budget."""
        if not self._model_loaded:
            raise TranslationError("Model not loaded")

        tokenizer = self.model_env["tokenizer"]
        lengths = [
            (
                p,
                len(
                    tokenizer(p, add_special_tokens=True, truncation=False)["input_ids"]
                ),
            )
            for p in pieces
        ]
        lengths.sort(key=lambda x: x[1], reverse=True)

        batches, cur_batch, cur_tokens = [], [], 0
        for p, t in lengths:
            if t > max_tokens_per_batch:
                # Put this piece alone
                if cur_batch:
                    batches.append(cur_batch)
                    cur_batch, cur_tokens = [], 0
                batches.append([p])
                continue
            if cur_tokens + t > max_tokens_per_batch and cur_batch:
                batches.append(cur_batch)
                cur_batch, cur_tokens = [], 0
            cur_batch.append(p)
            cur_tokens += t
        if cur_batch:
            batches.append(cur_batch)
        return batches

    @torch.inference_mode()
    def translate_batch(
        self, texts: List[str], max_new_tokens: int = None, num_beams: int = None
    ) -> List[str]:
        """Translate a batch of texts."""
        if not self._model_loaded:
            raise TranslationError("Model not loaded")

        if max_new_tokens is None:
            max_new_tokens = self.settings.max_new_tokens
        if num_beams is None:
            num_beams = self.settings.num_beams

        tokenizer = self.model_env["tokenizer"]
        model = self.model_env["model"]
        device = self.model_env["device"]
        forced_bos_id = self.model_env["forced_bos_id"]

        # Ensure source language is set
        if hasattr(tokenizer, "src_lang") and "src" in self.model_env:
            tokenizer.src_lang = self.model_env["src"]

        # Encode texts
        encoded = tokenizer(
            texts,
            padding=True,
            truncation=False,
            return_tensors="pt",
        )
        encoded = {k: v.to(device) for k, v in encoded.items()}

        # Generate translations
        with torch.autocast(
            device_type=device.type,
            dtype=self.model_env["dtype"] if device.type == "cuda" else torch.float32,
        ):
            generated = model.generate(
                **encoded,
                do_sample=False,
                num_beams=num_beams,
                max_new_tokens=max_new_tokens,
                forced_bos_token_id=forced_bos_id,
            )

        # Decode results
        results = tokenizer.batch_decode(generated, skip_special_tokens=True)
        return results

    def translate_texts_token_safe(self, texts: List[str]) -> List[str]:
        """Translate texts with token-aware chunking and batching."""
        if not self._model_loaded:
            raise TranslationError("Model not loaded")

        tokenizer = self.model_env["tokenizer"]
        results: List[str] = []

        for text in texts:
            pieces = self.chunk_by_tokens(text, self.settings.max_input_tokens)
            translated_chunks: List[str] = []

            if self.settings.max_tokens_per_batch > 0:
                batches = self.pack_by_token_budget(
                    pieces, self.settings.max_tokens_per_batch
                )
            else:
                # Fallback: count-based batching
                batches = list(self._batched(pieces, self.settings.batch_size))

            for batch in batches:
                translated_chunks.extend(
                    self.translate_batch(
                        batch, self.settings.max_new_tokens, self.settings.num_beams
                    )
                )

            results.append(" ".join(translated_chunks))

        return results

    @staticmethod
    def _batched(iterable: Iterable, n: int) -> Iterable[List]:
        """Batch an iterable into chunks of size n."""
        buf = []
        for x in iterable:
            buf.append(x)
            if len(buf) == n:
                yield buf
                buf = []
        if buf:
            yield buf


class MarkdownProcessor:
    """Handles markdown-specific processing and preservation."""

    @staticmethod
    def protect_tokens(text: str) -> Tuple[str, List[str]]:
        """Protect markdown tokens from translation."""
        stash = []

        def _stash(m):
            stash.append(m.group(0))
            return f"[[[TOKEN_{len(stash)-1}]]]"

        # Protect inline code and links/images
        text = INLINE_CODE_RE.sub(_stash, text)
        text = LINK_OR_IMG_RE.sub(_stash, text)
        return text, stash

    @staticmethod
    def restore_tokens(text: str, stash: List[str]) -> str:
        """Restore protected tokens."""

        def _restore(m: re.Match) -> str:
            return stash[int(m.group(1))]

        return PLACEHOLDER_RE.sub(_restore, text)

    @staticmethod
    def copy_referenced_images(md_text: str, md_dir: Path, out_dir: Path) -> None:
        """Copy images referenced in markdown to output directory."""
        seen = set()
        for m in IMG_LINK_RE.finditer(md_text):
            raw = m.group(1).strip()
            if raw.startswith(("http://", "https://", "data:")):
                continue
            path_str = raw.strip(" '\"<>")
            src = (md_dir / path_str).resolve()
            if not src.exists() or not src.is_file():
                continue
            if src in seen:
                continue
            seen.add(src)
            dst = (out_dir / path_str).resolve()
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                if src.resolve() != dst.resolve():
                    import shutil

                    shutil.copy2(src, dst)
                    logger.debug(f"Copied image: {src} -> {dst}")
            except Exception as e:
                logger.warning(f"Could not copy image {src} -> {dst}: {e}")


class DocumentTranslator:
    """High-level document translation orchestrator."""

    def __init__(self):
        self.translation_service = TranslationService()
        self.markdown_processor = MarkdownProcessor()

    def translate_markdown_document(
        self,
        md_text: str,
        out_dir: Optional[Path] = None,
        key: Optional[str] = None,
        flush_every: int = 20,
        progress_callback=None,
    ) -> str:
        """
        Translate a markdown document while preserving structure.

        Args:
            md_text: Markdown text to translate
            out_dir: Output directory for checkpoints
            key: Unique key for checkpoint
            flush_every: Save checkpoint every N blocks
            progress_callback: Function to call with progress updates

        Returns:
            Translated markdown text
        """
        logger.info("Starting markdown document translation")

        # Ensure model is loaded
        self.translation_service.load_model()

        # Split by fenced code blocks
        parts = FENCE_RE.split(md_text)
        out_parts: List[str] = []

        # Load checkpoint if available
        checkpoint = (
            self._load_checkpoint(out_dir, key)
            if (out_dir and key)
            else {"done": 0, "parts": []}
        )
        start_i = checkpoint.get("done", 0)
        if start_i > 0:
            out_parts = checkpoint["parts"][:start_i]
            logger.info(f"Resuming from part {start_i}/{len(parts)}")

        total_parts = len(parts)

        for i in tqdm(range(start_i, total_parts), desc="Translating blocks"):
            part = parts[i]

            if i % 2 == 1:  # Fenced code block - don't translate
                out_parts.append(part)
            else:
                # Translate regular text
                protected, stash = self.markdown_processor.protect_tokens(part)
                paragraphs = [p for p in re.split(r"(\n\s*\n)", protected)]

                # Map paragraphs to translation buffer
                mapping, buffer = [], []
                for idx, p in enumerate(paragraphs):
                    if p.strip() == "" or p.strip() == "\n":
                        mapping.append((idx, None))
                    else:
                        mapping.append((idx, p))
                        buffer.append(p)

                # Translate in batches
                translated: List[str] = []
                for batch in self.translation_service._batched(buffer, 8):
                    translated.extend(
                        self.translation_service.translate_texts_token_safe(batch)
                    )

                # Rebuild paragraphs
                t_iter = iter(translated)
                rebuilt = []
                for idx, original in mapping:
                    if original is None:
                        rebuilt.append(paragraphs[idx])
                    else:
                        rebuilt.append(
                            self.markdown_processor.restore_tokens(next(t_iter), stash)
                        )
                out_parts.append("".join(rebuilt))

            # Save checkpoint periodically
            if out_dir and key and ((i + 1) % flush_every == 0):
                checkpoint["key"] = key
                checkpoint["done"] = i + 1
                checkpoint["parts"] = out_parts
                self._save_checkpoint(out_dir, checkpoint)

            # Report progress
            if progress_callback:
                progress = ((i + 1) / total_parts) * 100
                progress_callback(progress)

        # Final checkpoint
        if out_dir and key:
            checkpoint["key"] = key
            checkpoint["done"] = len(parts)
            checkpoint["parts"] = out_parts
            self._save_checkpoint(out_dir, checkpoint)

        result = "".join(out_parts)
        logger.info("Markdown document translation completed")
        return result

    @staticmethod
    def _doc_key(file_path: Path) -> str:
        """Generate a unique key for a document."""
        h = hashlib.sha1(file_path.read_bytes()).hexdigest()
        return f"{file_path.name}:{h}"

    @staticmethod
    def _load_checkpoint(out_dir: Path, key: str) -> dict:
        """Load translation checkpoint."""
        checkpoint_file = out_dir / ".translate_checkpoint.json"
        if checkpoint_file.exists():
            try:
                data = json.loads(checkpoint_file.read_text())
                if data.get("key") == key:
                    return data
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return {"key": key, "done": 0, "parts": []}

    @staticmethod
    def _save_checkpoint(out_dir: Path, checkpoint: dict) -> None:
        """Save translation checkpoint."""
        checkpoint_file = out_dir / ".translate_checkpoint.json"
        try:
            checkpoint_file.write_text(json.dumps(checkpoint), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
