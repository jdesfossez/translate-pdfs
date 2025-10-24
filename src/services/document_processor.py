"""
Document processing pipeline for OCR, cleanup, and conversion.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.models.job import DocumentType

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Custom exception for document processing errors."""

    pass


class DocumentProcessor:
    """Handles the multi-stage document processing pipeline."""

    def __init__(self):
        self.settings = get_settings()

    def process_pdf(
        self,
        input_path: Path,
        output_dir: Path,
        document_type: DocumentType,
        progress_callback=None,
    ) -> Path:
        """
        Process a PDF through the complete pipeline.

        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
            document_type: Type of document processing needed
            progress_callback: Function to call with progress updates

        Returns:
            Path to the final translated PDF
        """
        logger.info(f"Starting PDF processing: {input_path} (type: {document_type})")

        # Create working directory
        work_dir = output_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Stage 1: OCR processing (if needed)
            if progress_callback:
                progress_callback(10, "Starting OCR processing...")

            if document_type in [DocumentType.TEXT_IMAGE_PDF, DocumentType.SCAN]:
                ocr_path = self._run_ocr(input_path, work_dir, document_type)
                if progress_callback:
                    progress_callback(30, "OCR processing completed")
            else:
                ocr_path = input_path
                if progress_callback:
                    progress_callback(30, "Skipping OCR (text PDF)")

            # Stage 2: Docling conversion
            if progress_callback:
                progress_callback(35, "Converting to Markdown...")

            md_path = self._run_docling(ocr_path, work_dir)
            if progress_callback:
                progress_callback(50, "Markdown conversion completed")

            # Stage 3: Translation
            if progress_callback:
                progress_callback(55, "Starting translation...")

            from src.services.translation_service import DocumentTranslator

            translator = DocumentTranslator()

            # Read markdown
            md_text = md_path.read_text(encoding="utf-8")

            # Translate with progress tracking
            def translation_progress(progress):
                # Translation takes 60-90% of total progress
                total_progress = 55 + (progress * 0.35)
                if progress_callback:
                    progress_callback(total_progress, f"Translating... {progress:.1f}%")

            translated_md = translator.translate_markdown_document(
                md_text,
                out_dir=work_dir,
                key=f"{input_path.stem}_{document_type.value}",
                progress_callback=translation_progress,
            )

            # Save translated markdown
            translated_md_path = work_dir / f"{input_path.stem}_fr.md"
            translated_md_path.write_text(translated_md, encoding="utf-8")

            if progress_callback:
                progress_callback(90, "Translation completed")

            # Stage 4: Copy images
            if progress_callback:
                progress_callback(92, "Copying images...")

            translator.markdown_processor.copy_referenced_images(
                md_text, md_path.parent, work_dir
            )

            # Stage 5: Generate final PDF
            if progress_callback:
                progress_callback(95, "Generating PDF...")

            final_pdf_path = self._generate_pdf(translated_md_path, output_dir)

            if progress_callback:
                progress_callback(100, "Processing completed")

            logger.info(f"PDF processing completed: {final_pdf_path}")
            return final_pdf_path

        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            raise DocumentProcessingError(f"Processing failed: {e}")

    def _run_ocr(
        self, input_path: Path, work_dir: Path, document_type: DocumentType
    ) -> Path:
        """Run OCR processing on the PDF."""
        output_path = work_dir / f"{input_path.stem}_ocred.pdf"

        # Build OCR command based on document type
        cmd = [
            "ocrmypdf",
            "--language",
            self.settings.ocr_language,
            "--output-type",
            "pdf",  # Avoid Ghostscript to prevent version 10.0.0 issues
            #"--force-ocr",  # Use force-ocr instead of skip-text to avoid Ghostscript regressions
        ]

        if document_type == DocumentType.SCAN:
            # Add cleanup options for scanned documents
            cmd.extend(["--rotate-pages", "--deskew", "--clean"])

        cmd.extend([str(input_path), str(output_path)])

        logger.info(f"Running OCR: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                raise DocumentProcessingError(f"OCR failed: {result.stderr}")

            logger.info("OCR processing completed successfully")
            return output_path

        except subprocess.TimeoutExpired:
            raise DocumentProcessingError("OCR processing timed out")
        except FileNotFoundError:
            raise DocumentProcessingError("ocrmypdf not found - please install it")

    def _run_docling(self, input_path: Path, work_dir: Path) -> Path:
        """Convert PDF to Markdown using Docling Python API."""
        output_dir = work_dir / "docling_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Running Docling conversion on: {input_path}")

        try:
            # Import docling components
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import (DocumentConverter,
                                                    PdfFormatOption)

            # Configure pipeline options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False  # We handle OCR separately
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True

            # Create converter with configuration using the new API
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                }
            )

            # Convert document
            logger.info("Starting Docling document conversion...")
            result = converter.convert(str(input_path))

            # Export to markdown
            md_filename = f"{input_path.stem}.md"
            md_path = output_dir / md_filename

            # Write markdown content
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(result.document.export_to_markdown())

            # Export images if any
            if hasattr(result.document, "pictures") and result.document.pictures:
                logger.info(f"Exporting {len(result.document.pictures)} images...")
                for i, picture in enumerate(result.document.pictures):
                    if picture.image:
                        img_filename = f"image_{i+1}.png"
                        img_path = output_dir / img_filename
                        picture.image.save(img_path)

            logger.info(f"Docling conversion completed: {md_path}")
            return md_path

        except ImportError as e:
            raise DocumentProcessingError(
                f"Docling import failed: {e}. Please ensure docling is properly installed."
            )
        except Exception as e:
            logger.error(f"Docling conversion error: {e}")
            raise DocumentProcessingError(f"Docling conversion failed: {e}")

    def _generate_pdf(self, md_path: Path, output_dir: Path) -> Path:
        """Generate PDF from translated markdown using Pandoc."""
        output_path = output_dir / f"{md_path.stem}.pdf"

        cmd = [
            "pandoc",
            str(md_path),
            "-o",
            str(output_path),
            "--toc",  # Table of contents
            "--pdf-engine=xelatex",  # Better Unicode support
        ]

        logger.info(f"Running Pandoc: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600  # 10 minutes timeout
            )

            if result.returncode != 0:
                raise DocumentProcessingError(f"PDF generation failed: {result.stderr}")

            logger.info(f"PDF generation completed: {output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            raise DocumentProcessingError("PDF generation timed out")
        except FileNotFoundError:
            raise DocumentProcessingError("pandoc not found - please install it")

    def cleanup_work_files(self, work_dir: Path) -> None:
        """Clean up temporary work files."""
        try:
            import shutil

            if work_dir.exists():
                shutil.rmtree(work_dir)
                logger.info(f"Cleaned up work directory: {work_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup work directory {work_dir}: {e}")
