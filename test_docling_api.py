#!/usr/bin/env python3
"""Test script to verify docling Python API works correctly."""

import sys
from pathlib import Path

def test_docling_import():
    """Test that docling can be imported and basic API works."""
    try:
        print("🔍 Testing docling imports...")
        
        # Test basic imports
        from docling.document_converter import DocumentConverter
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        print("✅ Basic docling imports successful")
        
        # Test pipeline options
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.do_table_structure = True
        print("✅ Pipeline options configuration successful")
        
        # Test converter creation
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: pipeline_options,
            }
        )
        print("✅ DocumentConverter creation successful")
        
        print("\n🎉 All docling API tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure docling and its dependencies are installed:")
        print("pip install docling>=1.0.0 docling-core>=1.7.0 docling-parse>=4.1.0")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_docling_version():
    """Test docling version information."""
    try:
        import docling
        print(f"📦 Docling version: {docling.__version__}")
        
        # Try to get more version info
        try:
            import docling_core
            print(f"📦 Docling-core version: {docling_core.__version__}")
        except:
            print("📦 Docling-core version: unknown")
            
        try:
            import docling_parse
            print(f"📦 Docling-parse version: {docling_parse.__version__}")
        except:
            print("📦 Docling-parse version: unknown")
            
    except Exception as e:
        print(f"❌ Version check failed: {e}")


def main():
    """Run all tests."""
    print("🧪 Testing Docling Python API")
    print("=" * 40)
    
    # Test version info
    test_docling_version()
    print()
    
    # Test API functionality
    success = test_docling_import()
    
    if success:
        print("\n✅ Docling is ready for use!")
        return 0
    else:
        print("\n❌ Docling setup has issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
