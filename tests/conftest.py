"""Test configuration and fixtures."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import Settings
from src.database import get_db
from src.models.job import Base


@pytest.fixture(scope="session")
def test_settings():
    """Test settings with temporary directories."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        settings = Settings(
            debug=True,
            upload_dir=temp_path / "uploads",
            output_dir=temp_path / "outputs", 
            database_url=f"sqlite:///{temp_path}/test.db",
            redis_url="redis://localhost:6379/15",  # Use test database
            model_name="facebook/mbart-large-50-many-to-many-mmt",  # Smaller model for tests
            max_file_size=10 * 1024 * 1024,  # 10MB for tests
        )
        
        # Create directories
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        
        yield settings


@pytest.fixture
def test_db(test_settings):
    """Test database session."""
    engine = create_engine(test_settings.database_url, echo=False)
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_settings, test_db):
    """Test client with dependency overrides."""
    from main import app
    
    # Override settings
    app.dependency_overrides[get_db] = lambda: test_db
    
    # Mock the settings
    import src.config
    original_get_settings = src.config.get_settings
    src.config.get_settings = lambda: test_settings
    
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Restore original settings
        src.config.get_settings = original_get_settings
        app.dependency_overrides.clear()


@pytest.fixture
def mock_translation_service():
    """Mock translation service for testing without GPU."""
    mock_service = Mock()
    mock_service.load_model.return_value = None
    mock_service.unload_model.return_value = None
    mock_service.translate_texts_token_safe.return_value = ["Texte traduit en français"]
    mock_service.count_tokens.return_value = 10
    mock_service.chunk_by_tokens.return_value = ["Test text"]
    return mock_service


@pytest.fixture
def mock_document_processor():
    """Mock document processor for testing without external tools."""
    mock_processor = Mock()
    mock_processor.process_pdf.return_value = Path("/fake/output.pdf")
    return mock_processor


@pytest.fixture
def sample_pdf_content():
    """Sample PDF content for testing."""
    # This is a minimal PDF content for testing
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Hello World) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
300
%%EOF"""


@pytest.fixture
def sample_markdown():
    """Sample markdown content for testing."""
    return """# Test Document

This is a test document with some **bold** text and *italic* text.

## Section 1

Here's a paragraph with some content.

```python
def hello():
    print("Hello, world!")
```

## Section 2

Another paragraph with a [link](https://example.com) and an image:

![Test Image](test.png)

- List item 1
- List item 2
- List item 3

| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
"""


@pytest.fixture(autouse=True)
def mock_external_tools(monkeypatch):
    """Mock external tools (OCR, Docling, Pandoc) for testing."""
    def mock_subprocess_run(*args, **kwargs):
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        return mock_result
    
    monkeypatch.setattr("subprocess.run", mock_subprocess_run)


@pytest.fixture
def mock_redis():
    """Mock Redis for testing."""
    mock_redis = Mock()
    mock_redis.from_url.return_value = mock_redis
    return mock_redis
