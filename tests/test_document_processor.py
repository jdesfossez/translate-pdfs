"""Tests for document processor."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.job import DocumentType
from src.services.document_processor import DocumentProcessor, DocumentProcessingError


class TestDocumentProcessor:
    """Test document processing functionality."""
    
    def test_init(self):
        """Test processor initialization."""
        processor = DocumentProcessor()
        assert processor.settings is not None
    
    @patch('subprocess.run')
    def test_run_ocr_text_image_pdf(self, mock_run, tmp_path):
        """Test OCR for text image PDF."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        result = processor._run_ocr(input_path, work_dir, DocumentType.TEXT_IMAGE_PDF)
        
        assert result.name.endswith("_ocred.pdf")
        mock_run.assert_called_once()
        
        # Check that basic OCR command was used
        cmd = mock_run.call_args[0][0]
        assert "ocrmypdf" in cmd
        assert "--force-ocr" in cmd  # Updated to use force-ocr instead of skip-text
        assert "--output-type" in cmd  # Added to avoid Ghostscript issues
        assert "pdf" in cmd  # The output type value
        assert "--rotate-pages" not in cmd  # Not for text image PDFs
    
    @patch('subprocess.run')
    def test_run_ocr_scan(self, mock_run, tmp_path):
        """Test OCR for scanned document."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        result = processor._run_ocr(input_path, work_dir, DocumentType.SCAN)
        
        assert result.name.endswith("_ocred.pdf")
        
        # Check that cleanup options were added for scans
        cmd = mock_run.call_args[0][0]
        assert "--rotate-pages" in cmd
        assert "--deskew" in cmd
        assert "--clean" in cmd
    
    @patch('subprocess.run')
    def test_run_ocr_failure(self, mock_run, tmp_path):
        """Test OCR failure handling."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "OCR failed"
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        with pytest.raises(DocumentProcessingError, match="OCR failed"):
            processor._run_ocr(input_path, work_dir, DocumentType.SCAN)
    
    @patch('subprocess.run')
    def test_run_ocr_timeout(self, mock_run, tmp_path):
        """Test OCR timeout handling."""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("ocrmypdf", 3600)
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        with pytest.raises(DocumentProcessingError, match="OCR processing timed out"):
            processor._run_ocr(input_path, work_dir, DocumentType.SCAN)
    
    @patch('src.services.document_processor.DocumentConverter')
    def test_run_docling_success(self, mock_converter_class, tmp_path):
        """Test successful Docling conversion using Python API."""
        # Mock the converter and result
        mock_converter = Mock()
        mock_converter_class.return_value = mock_converter

        mock_result = Mock()
        mock_document = Mock()
        mock_document.export_to_markdown.return_value = "# Test Document\n\nThis is a test."
        mock_result.document = mock_document
        mock_converter.convert.return_value = mock_result

        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        result = processor._run_docling(input_path, work_dir)

        # Check that the markdown file was created
        expected_path = work_dir / "docling_output" / "input.md"
        assert result == expected_path
        assert result.exists()
        assert "# Test Document" in result.read_text()

        # Verify converter was called correctly
        mock_converter_class.assert_called_once()
        mock_converter.convert.assert_called_once_with(str(input_path))
    
    @patch('subprocess.run')
    def test_run_docling_no_output(self, mock_run, tmp_path):
        """Test Docling with no output file."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        with pytest.raises(DocumentProcessingError, match="No markdown file generated"):
            processor._run_docling(input_path, work_dir)
    
    @patch('subprocess.run')
    def test_generate_pdf_success(self, mock_run, tmp_path):
        """Test successful PDF generation."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""
        
        processor = DocumentProcessor()
        md_path = tmp_path / "test_fr.md"
        md_path.write_text("# Document Traduit")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        result = processor._generate_pdf(md_path, output_dir)
        
        assert result.name == "test_fr.pdf"
        mock_run.assert_called_once()
        
        # Check command
        cmd = mock_run.call_args[0][0]
        assert "pandoc" in cmd
        assert "--toc" in cmd
    
    @patch('subprocess.run')
    def test_generate_pdf_failure(self, mock_run, tmp_path):
        """Test PDF generation failure."""
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Pandoc failed"
        
        processor = DocumentProcessor()
        md_path = tmp_path / "test_fr.md"
        md_path.write_text("# Document Traduit")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        with pytest.raises(DocumentProcessingError, match="PDF generation failed"):
            processor._generate_pdf(md_path, output_dir)
    
    @patch('shutil.rmtree')
    def test_cleanup_work_files(self, mock_rmtree, tmp_path):
        """Test work file cleanup."""
        processor = DocumentProcessor()
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        processor.cleanup_work_files(work_dir)
        
        mock_rmtree.assert_called_once_with(work_dir)
    
    @patch('src.services.document_processor.DocumentProcessor._run_ocr')
    @patch('src.services.document_processor.DocumentProcessor._run_docling')
    @patch('src.services.document_processor.DocumentProcessor._generate_pdf')
    @patch('src.services.translation_service.DocumentTranslator')
    def test_process_pdf_text_pdf(self, mock_translator_class, mock_gen_pdf, 
                                 mock_docling, mock_ocr, tmp_path):
        """Test processing text PDF (no OCR needed)."""
        # Setup mocks
        mock_translator = Mock()
        mock_translator.translate_markdown_document.return_value = "# Translated"
        mock_translator.markdown_processor.copy_referenced_images.return_value = None
        mock_translator_class.return_value = mock_translator
        
        md_path = tmp_path / "test.md"
        md_path.write_text("# Test")
        mock_docling.return_value = md_path
        
        final_pdf = tmp_path / "final.pdf"
        mock_gen_pdf.return_value = final_pdf
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        output_dir = tmp_path / "output"
        
        progress_calls = []
        def progress_callback(progress, stage):
            progress_calls.append((progress, stage))
        
        result = processor.process_pdf(
            input_path, 
            output_dir, 
            DocumentType.TEXT_PDF,
            progress_callback
        )
        
        # OCR should be skipped for text PDFs
        mock_ocr.assert_not_called()
        mock_docling.assert_called_once()
        mock_gen_pdf.assert_called_once()
        
        assert len(progress_calls) > 0
        assert result == final_pdf
    
    @patch('src.services.document_processor.DocumentProcessor._run_ocr')
    @patch('src.services.document_processor.DocumentProcessor._run_docling')
    @patch('src.services.document_processor.DocumentProcessor._generate_pdf')
    @patch('src.services.translation_service.DocumentTranslator')
    def test_process_pdf_with_ocr(self, mock_translator_class, mock_gen_pdf, 
                                 mock_docling, mock_ocr, tmp_path):
        """Test processing PDF that needs OCR."""
        # Setup mocks
        mock_translator = Mock()
        mock_translator.translate_markdown_document.return_value = "# Translated"
        mock_translator.markdown_processor.copy_referenced_images.return_value = None
        mock_translator_class.return_value = mock_translator
        
        ocr_path = tmp_path / "ocred.pdf"
        mock_ocr.return_value = ocr_path
        
        md_path = tmp_path / "test.md"
        md_path.write_text("# Test")
        mock_docling.return_value = md_path
        
        final_pdf = tmp_path / "final.pdf"
        mock_gen_pdf.return_value = final_pdf
        
        processor = DocumentProcessor()
        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"fake pdf")
        output_dir = tmp_path / "output"
        
        result = processor.process_pdf(
            input_path, 
            output_dir, 
            DocumentType.SCAN
        )
        
        # OCR should be called for scanned documents
        mock_ocr.assert_called_once()
        mock_docling.assert_called_once_with(ocr_path, output_dir / "work")
        mock_gen_pdf.assert_called_once()
        
        assert result == final_pdf
