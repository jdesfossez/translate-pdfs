#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate_gpu.py — Legacy CLI script for translating Docling Markdown EN→FR on GPU.

This file is being refactored into a web service. The core translation logic
will be moved to src/services/translation_service.py

Usage:
  python translate_gpu.py /path/to/docling/file.md \
      --out-dir out --copy-images --batch-size 48 --max-input-tokens 950

Docling examples:
  docling --from pdf --to md --image-export-mode referenced --pdf-backend dlparse_v4 \
          --no-ocr --num-threads 8 --device auto --output out your.pdf
"""

import argparse, os, re, sys, shutil, html, json, hashlib, math, platform
from pathlib import Path
from typing import List, Tuple, Iterable, Optional
from tqdm import tqdm
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, AutoConfig, AutoModelForSeq2SeqLM
from accelerate import init_empty_weights, load_checkpoint_and_dispatch

PLACEHOLDER_RE = re.compile(r"\[\[\[TOKEN_(\d+)\]\]\]")

# ---- GPU speed knobs (safe on CPU too) ---------------------------------------
import torch
torch.backends.cuda.matmul.allow_tf32 = True
torch.set_float32_matmul_precision("high")  # enables TF32 on Hopper/Ampere

def pack_by_token_budget(pieces: List[str], tokenizer, max_tokens_per_batch: int) -> List[List[str]]:
    """
    Greedy pack: sort by length (desc), then fill batches until the token budget is reached.
    """
    lengths = [(p, len(tokenizer(p, add_special_tokens=True, truncation=False)["input_ids"])) for p in pieces]
    lengths.sort(key=lambda x: x[1], reverse=True)

    batches, cur_batch, cur_tokens = [], [], 0
    for p, t in lengths:
        if t > max_tokens_per_batch:
            # fall back: put this alone (it still fits because each piece <= max_input_tokens)
            if cur_batch:
                batches.append(cur_batch); cur_batch, cur_tokens = [], 0
            batches.append([p])
            continue
        if cur_tokens + t > max_tokens_per_batch and cur_batch:
            batches.append(cur_batch); cur_batch, cur_tokens = [], 0
        cur_batch.append(p); cur_tokens += t
    if cur_batch:
        batches.append(cur_batch)
    return batches


# ---- Small helpers -----------------------------------------------------------
def batched(iterable: Iterable, n: int) -> Iterable[List]:
    buf = []
    for x in iterable:
        buf.append(x)
        if len(buf) == n:
            yield buf; buf = []
    if buf: yield buf

def doc_key(p: Path) -> str:
    h = hashlib.sha1(p.read_bytes()).hexdigest()
    return f"{p.name}:{h}"

def load_checkpoint(out_dir: Path, key: str):
    ck = out_dir / ".translate_checkpoint.json"
    if ck.exists():
        try:
            data = json.loads(ck.read_text())
            if data.get("key") == key:
                return data
        except Exception:
            pass
    return {"key": key, "done": 0, "parts": []}

def save_checkpoint(out_dir: Path, ck):
    (out_dir / ".translate_checkpoint.json").write_text(json.dumps(ck), encoding="utf-8")

# ---- Markdown preservation ---------------------------------------------------
FENCE_RE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_OR_IMG_RE = re.compile(r"(!?$begin:math:display$[^$end:math:display$]*\]$begin:math:text$[^)]+$end:math:text$)")  # links+images

def protect_tokens(text: str):
	stash = []
	def _stash(m):
		stash.append(m.group(0))
		return f"[[[TOKEN_{len(stash)-1}]]]"
	t = INLINE_CODE_RE.sub(_stash, text)
	t = LINK_OR_IMG_RE.sub(_stash, t)
	return t, stash

def restore_tokens(text: str, stash: list[str]) -> str:
    def _restore(m: re.Match) -> str:
        return stash[int(m.group(1))]
    return PLACEHOLDER_RE.sub(_restore, text)

# ---- Token-aware chunking ----------------------------------------------------
def count_tokens(text: str, tokenizer) -> int:
    return len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])

def chunk_by_tokens(text: str, tokenizer, max_tokens: int = 900) -> List[str]:
    # Simple sentence split; robust enough for tech prose
    sents = re.split(r"(?<=[\.\?!])\s+", text)
    chunks, buf, buf_tokens = [], [], 0

    for s in sents:
        t = count_tokens(s, tokenizer)
        if t > max_tokens:
            # Hard split long "sentence" by words
            words = s.split()
            cur = []
            for w in words:
                candidate = " ".join(cur + [w])
                tw = count_tokens(candidate, tokenizer)
                if tw > max_tokens and cur:
                    chunks.append(" ".join(cur)); cur = [w]
                else:
                    cur.append(w)
            if cur: chunks.append(" ".join(cur))
            continue

        if buf_tokens + t <= max_tokens:
            buf.append(s); buf_tokens += t
        else:
            if buf: chunks.append(" ".join(buf))
            buf, buf_tokens = [s], t

    if buf: chunks.append(" ".join(buf))
    return chunks

# ---- Image copying (optional) ------------------------------------------------
IMG_LINK_RE = re.compile(r"!$begin:math:display$[^$end:math:display$]*\]$begin:math:text$([^)]+)$end:math:text$")

def copy_referenced_images(md_text: str, md_dir: Path, out_dir: Path) -> None:
    seen = set()
    for m in IMG_LINK_RE.finditer(md_text):
        raw = m.group(1).strip()
        if raw.startswith(("http://", "https://", "data:")):
            continue
        path_str = raw.strip(' \'"<>')
        src = (md_dir / path_str).resolve()
        if not src.exists() or not src.is_file(): continue
        if src in seen: continue
        seen.add(src)
        dst = (out_dir / path_str).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
        except Exception as e:
            print(f"[warn] Could not copy image {src} -> {dst}: {e}", file=sys.stderr)

def load_model(model_name, revision=None, use_safetensors=False, cpu_load_then_gpu=False):
    # Only fetch safetensors + tokenizer/config
    repo_dir = snapshot_download(
        repo_id=model_name,
        revision=revision,
        allow_patterns=[
            "config.json",
            "generation_config.json",
            "model.safetensors.index.json",
            "model-*.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
            # some repos also have these names:
            "source.spm", "target.spm"
        ],
        ignore_patterns=["pytorch_model.bin.index.json", "*.bin", "*.pt"],
    )

    tok = AutoTokenizer.from_pretrained(repo_dir)
    cfg = AutoConfig.from_pretrained(repo_dir)

    # init empty -> dispatch safetensors directly to GPU (no .to(meta))
    with init_empty_weights():
        mdl = AutoModelForSeq2SeqLM.from_config(cfg)
    mdl.tie_weights()

    device_map = {"": "cuda"} if torch.cuda.is_available() else {"": "cpu"}
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    mdl = load_checkpoint_and_dispatch(
        mdl, checkpoint=repo_dir, device_map=device_map, dtype=dtype
    ).eval()

    # Language setup
    if "nllb" in model_name:
        src, tgt = "eng_Latn", "fra_Latn"
        # set source language ON THE TOKENIZER
        if hasattr(tok, "src_lang"):
            tok.src_lang = src
        # get BOS for target language
        forced_bos_id = getattr(tok, "lang_code_to_id", {}).get(tgt, tok.convert_tokens_to_ids(tgt))

    elif "mbart" in model_name:
        src, tgt = "en_XX", "fr_XX"
        if hasattr(tok, "src_lang"):
            tok.src_lang = src
        forced_bos_id = tok.lang_code_to_id[tgt]

    else:
        raise ValueError("Unsupported model; use mBART-50 or NLLB-200 variants.")

    # optional: remove legacy flag
    try:
        if hasattr(mdl.generation_config, "early_stopping"):
            delattr(mdl.generation_config, "early_stopping")
    except Exception:
        pass

    return {
        "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
        "dtype": dtype,
        "tokenizer": tok,
        "model": mdl,
        "src": src, "tgt": tgt,
        "forced_bos_id": forced_bos_id,
        "model_name": model_name,
    }

# ---- Generation in batches (no pipeline) ------------------------------------
@torch.inference_mode()
def translate_batch(texts: List[str], env, max_new_tokens: int = 400, num_beams: int = 1):
    tok = env["tokenizer"]
    mdl = env["model"]
    dev = env["device"]
    bos = env["forced_bos_id"]

    # ensure src_lang is set (harmless to set repeatedly)
    if hasattr(tok, "src_lang") and "src" in env:
        tok.src_lang = env["src"]

    enc = tok(
            texts,
            padding=True,
            truncation=False,      # we chunk beforehand
            return_tensors="pt",
            )
    enc = {k: v.to(dev) for k, v in enc.items()}

    with torch.autocast(device_type=dev.type, dtype=env["dtype"] if dev.type == "cuda" else torch.float32):
        gen = mdl.generate(
                **enc,
                do_sample=False,
                num_beams=num_beams,
                max_new_tokens=max_new_tokens,
                forced_bos_token_id=bos,
                )
    out = tok.batch_decode(gen, skip_special_tokens=True)
    return out

def translate_texts_token_safe(texts: List[str], env, max_input_tokens: int, batch_size: int,
                               max_new_tokens: int = 400, num_beams: int = 1,
                               max_tokens_per_batch: int = 0) -> List[str]:
    tok = env["tokenizer"]
    results: List[str] = []
    for text in texts:
        pieces = chunk_by_tokens(text, tok, max_tokens=max_input_tokens)
        translated_chunks: List[str] = []

        if max_tokens_per_batch and max_tokens_per_batch > 0:
            batches = pack_by_token_budget(pieces, tok, max_tokens_per_batch)
        else:
            # fallback: count-based batching
            batches = list(batched(pieces, batch_size))

        for sub in batches:
            translated_chunks.extend(
                translate_batch(sub, env, max_new_tokens=max_new_tokens, num_beams=num_beams)
            )
        results.append(" ".join(translated_chunks))
    return results

# ---- Main Markdown translation flow -----------------------------------------
def translate_blocks(md_text: str, translate_fn, tokenizer, max_input_tokens: int,
                     out_dir: Optional[Path] = None, key: Optional[str] = None,
                     flush_every: int = 20) -> str:
    """
    Preserve fenced code blocks & tokens; translate non-code spans with batching & chunking.
    """
    parts = FENCE_RE.split(md_text)
    out_parts: List[str] = []

    ck = load_checkpoint(out_dir, key) if (out_dir and key) else {"done": 0, "parts": []}
    start_i = ck.get("done", 0)
    if start_i > 0:
        out_parts = ck["parts"][:start_i]
        print(f"[resume] Resuming from part {start_i}/{len(parts)}")

    for i in tqdm(range(start_i, len(parts)), desc="Translating blocks"):
        part = parts[i]
        if i % 2 == 1:  # fenced code
            out_parts.append(part)
        else:
            protected, stash = protect_tokens(part)
            paras = [p for p in re.split(r"(\n\s*\n)", protected)]
            mapping, buffer = [], []
            for idx, p in enumerate(paras):
                if p.strip() == "" or p.strip() == "\n":
                    mapping.append((idx, None))
                else:
                    mapping.append((idx, p)); buffer.append(p)

            translated: List[str] = []
            for pack in batched(buffer, 8):
                translated.extend(translate_fn(pack, tokenizer, max_input_tokens))

            t_iter = iter(translated)
            rebuilt = []
            for idx, original in mapping:
                if original is None:
                    rebuilt.append(paras[idx])
                else:
                    rebuilt.append(restore_tokens(next(t_iter), stash))
            out_parts.append("".join(rebuilt))

        if out_dir and key and ((i + 1) % flush_every == 0):
            ck["key"] = key; ck["done"] = i + 1; ck["parts"] = out_parts
            save_checkpoint(out_dir, ck)

    if out_dir and key:
        ck["key"] = key; ck["done"] = len(parts); ck["parts"] = out_parts
        save_checkpoint(out_dir, ck)

    return "".join(out_parts)

# ---- CLI --------------------------------------------------------------------
def main():
    from markdown import markdown

    ap = argparse.ArgumentParser(description="Translate Docling Markdown EN→FR (GPU, chunked) and build HTML.")
    ap.add_argument("md_path", type=Path, help="Path to Docling-generated .md")
    ap.add_argument("--out-dir", type=Path, default=None, help="Output dir (default: md dir)")
    ap.add_argument("--title", default="Document traduit (FR)")
    ap.add_argument("--model", default="facebook/mbart-large-50-many-to-many-mmt",
                    help="e.g., facebook/mbart-large-50-many-to-many-mmt or facebook/nllb-200-distilled-1.3B")
    ap.add_argument("--max-input-tokens", type=int, default=950, help="<= 1024 (mBART) or ~1024 (NLLB 1.3B)")
    ap.add_argument("--max-new-tokens", type=int, default=400, help="Output cap per chunk")
    ap.add_argument("--num-beams", type=int, default=1, help="1=greedy (fast), 2–3 for a touch more polish")
    ap.add_argument("--batch-size", type=int, default=48, help="GPU sub-batch size for chunk translation")
    ap.add_argument("--copy-images", action="store_true", help="Copy local images into out-dir")
    ap.add_argument("--max-tokens-per-batch", type=int, default=32000,
            help="Pack pieces by total source tokens per batch (overrides --batch-size if set)")
    ap.add_argument("--revision", default=None, help="HF revision/branch/tag, e.g. refs/pr/17")
    ap.add_argument("--use-safetensors", action="store_true", help="Force safetensors if available")
    ap.add_argument("--cpu-load-then-gpu", action="store_true",
            help="Load weights on CPU (no meta) then move to GPU. Use for big models like nllb-200-3.3B.")

    args = ap.parse_args()

    md_path: Path = args.md_path
    if not md_path.exists():
        print(f"Markdown not found: {md_path}", file=sys.stderr); return 2

    md_dir = md_path.parent.resolve()
    out_dir = args.out_dir.resolve() if args.out_dir else md_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load MD
    md_text = md_path.read_text(encoding="utf-8")

    # Load model/tokenizer
    #env = load_model(args.model)
    env = load_model(args.model, revision=args.revision,
                     use_safetensors=args.use_safetensors,
                     cpu_load_then_gpu=args.cpu_load_then_gpu)
    tok = env["tokenizer"]
    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device_str} | Model: {env['model_name']} | Arch: {platform.machine()}")

    # Translation function wiring
    def translate_fn(batch_texts: List[str], tokenizer, max_input_tokens: int) -> List[str]:
        return translate_texts_token_safe(
                batch_texts, env,
                max_input_tokens=max_input_tokens,
                batch_size=args.batch_size,
                max_new_tokens=args.max_new_tokens,
                num_beams=args.num_beams,
                max_tokens_per_batch=args.max_tokens_per_batch
                )

    # Translate (with checkpoint)
    key = doc_key(md_path)
    print("Translating… This may take a while for a 500-page doc.")
    fr_text = translate_blocks(md_text, translate_fn, tok, args.max_input_tokens,
                               out_dir=out_dir, key=key, flush_every=20)

    # Write FR Markdown
    fr_md_path = out_dir / f"{md_path.stem}_fr.md"
    fr_md_path.write_text(fr_text, encoding="utf-8")
    print(f"Wrote {fr_md_path}")

    # Images
    if args.copy_images:
        copy_referenced_images(md_text, md_dir, out_dir)

    # HTML viewer
    html_body = markdown(fr_text, extensions=["extra", "tables", "toc"])
    html_page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(args.title)}</title>
  <style>
    body {{ max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.55; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
    img {{ max-width: 100%; height: auto; }}
    pre, code {{ background: #f6f8fa; }}
    pre {{ overflow: auto; padding: .75rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    table, th, td {{ border: 1px solid #ddd; }}
    th, td {{ padding: .4rem .6rem; vertical-align: top; }}
    h1, h2, h3 {{ margin-top: 1.6em; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""
    html_path = out_dir / "index.html"
    html_path.write_text(html_page, encoding="utf-8")
    print(f"Wrote {html_path}  ← open in your browser")
    return 0

if __name__ == "__main__":
    sys.exit(main())
