# API Documentation

The PDF Translation Service provides a RESTful API for programmatic access to translation functionality.

## Base URL

```
http://localhost:8000/api
```

## Authentication

Currently, the API does not require authentication. In production, consider adding API keys or OAuth.

## Endpoints

### Health Check

#### GET /health

Check service health and GPU availability.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "gpu_available": true,
  "gpu_count": 1,
  "version": "1.0.0"
}
```

#### GET /health/ready

Check if service is ready to accept requests.

**Response:**
```json
{
  "status": "ready",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Job Management

#### POST /api/jobs

Create a new translation job.

**Request:**
- Content-Type: `multipart/form-data`
- Body:
  - `file`: PDF file (required)
  - `document_type`: Document type (required)

**Document Types:**
- `text_pdf`: PDF with selectable text
- `text_image_pdf`: PDF with clean text images (needs OCR)
- `scan`: Scanned document (needs OCR and cleanup)

**Example:**
```bash
curl -X POST "http://localhost:8000/api/jobs" \
  -F "file=@document.pdf" \
  -F "document_type=text_pdf"
```

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "document.pdf",
  "document_type": "text_pdf",
  "status": "pending",
  "stage": "uploaded",
  "progress": 0.0,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "error_message": null,
  "output_files": []
}
```

#### GET /api/jobs

List all translation jobs.

**Response:**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "filename": "document.pdf",
    "document_type": "text_pdf",
    "status": "completed",
    "stage": "completed",
    "progress": 100.0,
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z",
    "error_message": null,
    "output_files": ["document_fr.pdf", "document_fr.md"]
  }
]
```

#### GET /api/jobs/{job_id}

Get details of a specific job.

**Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "document.pdf",
  "document_type": "text_pdf",
  "status": "processing",
  "stage": "translation",
  "progress": 65.5,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:33:00Z",
  "error_message": null,
  "output_files": []
}
```

#### DELETE /api/jobs/{job_id}

Cancel a pending or processing job.

**Response:**
```json
{
  "message": "Job cancelled"
}
```

#### GET /api/jobs/{job_id}/download/{filename}

Download an output file from a completed job.

**Response:**
- Content-Type: `application/octet-stream`
- File content as binary data

## Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request (wrong file type, missing parameters)
- `404 Not Found`: Job or file not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

## Job Status Values

### Status
- `pending`: Job queued for processing
- `processing`: Job currently being processed
- `completed`: Job finished successfully
- `failed`: Job failed with error
- `cancelled`: Job was cancelled

### Stage
- `uploaded`: File uploaded, waiting to start
- `ocr_processing`: Running OCR on document
- `docling_conversion`: Converting PDF to Markdown
- `translation`: Translating content
- `pdf_generation`: Generating final PDF
- `completed`: All processing complete

## Error Responses

### Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "document_type"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### File Too Large
```json
{
  "detail": "File too large"
}
```

### Job Not Found
```json
{
  "detail": "Job not found"
}
```

### Processing Error
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "failed",
  "error_message": "OCR processing failed: Unable to process PDF"
}
```

## Rate Limiting

Currently no rate limiting is implemented. Consider adding rate limiting in production:

- File uploads: 10 per hour per IP
- API calls: 100 per minute per IP

## WebSocket Support (Future)

Real-time progress updates via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/jobs/{job_id}');
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Progress:', data.progress);
};
```

## SDK Examples

### Python

```python
import requests

# Upload document
with open('document.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/jobs',
        files={'file': f},
        data={'document_type': 'text_pdf'}
    )
    job = response.json()

# Check status
job_id = job['id']
status = requests.get(f'http://localhost:8000/api/jobs/{job_id}').json()

# Download result (when completed)
if status['status'] == 'completed':
    for filename in status['output_files']:
        response = requests.get(
            f'http://localhost:8000/api/jobs/{job_id}/download/{filename}'
        )
        with open(f'translated_{filename}', 'wb') as f:
            f.write(response.content)
```

### JavaScript

```javascript
// Upload document
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('document_type', 'text_pdf');

const response = await fetch('/api/jobs', {
    method: 'POST',
    body: formData
});
const job = await response.json();

// Poll for completion
const pollStatus = async (jobId) => {
    const response = await fetch(`/api/jobs/${jobId}`);
    const status = await response.json();
    
    if (status.status === 'completed') {
        // Download files
        for (const filename of status.output_files) {
            const link = document.createElement('a');
            link.href = `/api/jobs/${jobId}/download/${filename}`;
            link.download = filename;
            link.click();
        }
    } else if (status.status === 'processing') {
        // Continue polling
        setTimeout(() => pollStatus(jobId), 5000);
    }
};

pollStatus(job.id);
```

### cURL Examples

```bash
# Upload document
curl -X POST "http://localhost:8000/api/jobs" \
  -F "file=@document.pdf" \
  -F "document_type=scan" \
  -o job_response.json

# Extract job ID
JOB_ID=$(cat job_response.json | jq -r '.id')

# Check status
curl "http://localhost:8000/api/jobs/$JOB_ID" | jq '.'

# Download translated PDF (when ready)
curl "http://localhost:8000/api/jobs/$JOB_ID/download/document_fr.pdf" \
  -o translated_document.pdf
```

## Batch Processing

For processing multiple documents:

```python
import asyncio
import aiohttp

async def upload_document(session, filepath, doc_type):
    with open(filepath, 'rb') as f:
        data = aiohttp.FormData()
        data.add_field('file', f, filename=filepath.name)
        data.add_field('document_type', doc_type)
        
        async with session.post('/api/jobs', data=data) as response:
            return await response.json()

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [
            upload_document(session, 'doc1.pdf', 'text_pdf'),
            upload_document(session, 'doc2.pdf', 'scan'),
            upload_document(session, 'doc3.pdf', 'text_image_pdf'),
        ]
        jobs = await asyncio.gather(*tasks)
        
        # Monitor all jobs
        for job in jobs:
            print(f"Uploaded: {job['filename']} -> {job['id']}")
```

## Integration Examples

### Webhook Notifications (Future Feature)

```json
{
  "webhook_url": "https://your-app.com/webhook",
  "events": ["job.completed", "job.failed"]
}
```

### Queue Integration

Direct Redis queue access for advanced use cases:

```python
import redis
from rq import Queue

redis_conn = redis.from_url('redis://localhost:6379/0')
queue = Queue('pdf_translation', connection=redis_conn)

# Get queue status
print(f"Jobs in queue: {len(queue)}")
print(f"Failed jobs: {len(queue.failed_job_registry)}")
```

## Docker Compose Commands

For development and deployment:

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Restart specific service
docker compose restart worker
```
