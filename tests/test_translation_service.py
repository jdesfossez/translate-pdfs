"""Tests for translation service."""

from unittest.mock import Mock, patch

import pytest
import torch

from src.services.translation_service import (
    TranslationService, 
    MarkdownProcessor, 
    DocumentTranslator,
    TranslationError
)


class TestTranslationService:
    """Test translation service functionality."""
    
    @patch('torch.cuda.is_available')
    @patch('src.services.translation_service.snapshot_download')
    @patch('src.services.translation_service.AutoTokenizer')
    @patch('src.services.translation_service.AutoConfig')
    @patch('src.services.translation_service.AutoModelForSeq2SeqLM')
    def test_load_model_success(self, mock_model, mock_config, mock_tokenizer, 
                               mock_download, mock_cuda):
        """Test successful model loading."""
        mock_cuda.return_value = False  # Use CPU for testing
        mock_download.return_value = "/fake/model/path"
        
        # Mock tokenizer
        mock_tok = Mock()
        mock_tok.lang_code_to_id = {"fr_XX": 123}
        mock_tokenizer.from_pretrained.return_value = mock_tok
        
        # Mock config
        mock_cfg = Mock()
        mock_config.from_pretrained.return_value = mock_cfg
        
        # Mock model
        mock_mdl = Mock()
        mock_model.from_config.return_value = mock_mdl
        
        service = TranslationService()
        service.load_model()
        
        assert service._model_loaded is True
        assert service.model_env is not None
        assert service.model_env["device"].type == "cpu"
    
    def test_load_model_unsupported(self):
        """Test loading unsupported model."""
        with patch('src.config.get_settings') as mock_settings:
            mock_settings.return_value.model_name = "unsupported/model"
            
            service = TranslationService()
            with pytest.raises(TranslationError, match="Unsupported model"):
                service.load_model()
    
    def test_unload_model(self):
        """Test model unloading."""
        service = TranslationService()
        service.model_env = {"fake": "data"}
        service._model_loaded = True
        
        service.unload_model()
        
        assert service.model_env is None
        assert service._model_loaded is False
    
    def test_count_tokens_no_model(self):
        """Test token counting without loaded model."""
        service = TranslationService()
        
        with pytest.raises(TranslationError, match="Model not loaded"):
            service.count_tokens("test text")
    
    def test_chunk_by_tokens_no_model(self):
        """Test chunking without loaded model."""
        service = TranslationService()
        
        with pytest.raises(TranslationError, match="Model not loaded"):
            service.chunk_by_tokens("test text")
    
    def test_translate_batch_no_model(self):
        """Test batch translation without loaded model."""
        service = TranslationService()
        
        with pytest.raises(TranslationError, match="Model not loaded"):
            service.translate_batch(["test text"])


class TestMarkdownProcessor:
    """Test markdown processing functionality."""
    
    def test_protect_tokens(self):
        """Test token protection."""
        text = "Here is `inline code` and a [link](url) and ![image](img.png)"
        
        protected, stash = MarkdownProcessor.protect_tokens(text)
        
        assert "[[[TOKEN_0]]]" in protected
        assert "[[[TOKEN_1]]]" in protected
        assert "[[[TOKEN_2]]]" in protected
        assert len(stash) == 3
        assert "`inline code`" in stash
        assert "[link](url)" in stash
        assert "![image](img.png)" in stash
    
    def test_restore_tokens(self):
        """Test token restoration."""
        stash = ["`code`", "[link](url)", "![img](pic.png)"]
        text = "Text with [[[TOKEN_0]]] and [[[TOKEN_1]]] and [[[TOKEN_2]]]"
        
        restored = MarkdownProcessor.restore_tokens(text, stash)
        
        assert restored == "Text with `code` and [link](url) and ![img](pic.png)"
    
    @patch('shutil.copy2')
    def test_copy_referenced_images(self, mock_copy, tmp_path):
        """Test image copying."""
        # Create test files
        md_dir = tmp_path / "md"
        md_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        
        img_file = md_dir / "test.png"
        img_file.write_bytes(b"fake image data")
        
        md_text = "![Test Image](test.png)"
        
        MarkdownProcessor.copy_referenced_images(md_text, md_dir, out_dir)
        
        mock_copy.assert_called_once()
    
    def test_copy_referenced_images_skip_urls(self, tmp_path):
        """Test that URLs are skipped during image copying."""
        md_dir = tmp_path / "md"
        md_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        
        md_text = "![Web Image](https://example.com/image.png)"
        
        # Should not raise any errors
        MarkdownProcessor.copy_referenced_images(md_text, md_dir, out_dir)


class TestDocumentTranslator:
    """Test document translator functionality."""
    
    @patch('src.services.translation_service.TranslationService')
    def test_translate_markdown_document(self, mock_service_class):
        """Test markdown document translation."""
        # Mock the translation service
        mock_service = Mock()
        mock_service.load_model.return_value = None
        mock_service.translate_texts_token_safe.return_value = ["Texte traduit"]
        mock_service._batched.return_value = [["Test text"]]
        mock_service_class.return_value = mock_service
        
        translator = DocumentTranslator()
        
        md_text = """# Test
        
This is a test paragraph.

```python
print("code")
```

Another paragraph."""
        
        result = translator.translate_markdown_document(md_text)
        
        assert "Texte traduit" in result
        assert "```python" in result  # Code blocks should be preserved
        assert "print(\"code\")" in result
    
    @patch('src.services.translation_service.TranslationService')
    def test_translate_with_progress_callback(self, mock_service_class):
        """Test translation with progress callback."""
        mock_service = Mock()
        mock_service.load_model.return_value = None
        mock_service.translate_texts_token_safe.return_value = ["Translated"]
        mock_service._batched.return_value = [["Text"]]
        mock_service_class.return_value = mock_service
        
        translator = DocumentTranslator()
        
        progress_calls = []
        def progress_callback(progress):
            progress_calls.append(progress)
        
        md_text = "# Test\n\nSimple text."
        
        translator.translate_markdown_document(
            md_text, 
            progress_callback=progress_callback
        )
        
        assert len(progress_calls) > 0
        assert all(0 <= p <= 100 for p in progress_calls)
    
    def test_doc_key_generation(self, tmp_path):
        """Test document key generation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        key = DocumentTranslator._doc_key(test_file)
        
        assert "test.txt:" in key
        assert len(key.split(":")[1]) == 40  # SHA1 hash length
    
    def test_checkpoint_operations(self, tmp_path):
        """Test checkpoint save and load."""
        checkpoint = {"key": "test", "done": 5, "parts": ["part1", "part2"]}
        
        DocumentTranslator._save_checkpoint(tmp_path, checkpoint)
        loaded = DocumentTranslator._load_checkpoint(tmp_path, "test")
        
        assert loaded == checkpoint
    
    def test_checkpoint_load_nonexistent(self, tmp_path):
        """Test loading non-existent checkpoint."""
        loaded = DocumentTranslator._load_checkpoint(tmp_path, "nonexistent")
        
        assert loaded == {"key": "nonexistent", "done": 0, "parts": []}
