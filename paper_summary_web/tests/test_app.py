import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as server
from summarizer import UserFacingError, extract_document

client = TestClient(server.app)


def test_home():
    assert client.get('/').status_code == 200
    assert 'PaperBrief' in client.get('/').text


def test_bad_extension():
    r = client.post('/api/summarize', files={'file': ('slides.pptx', b'not a ppt', 'application/octet-stream')})
    assert r.status_code == 415
    assert 'PDF' in r.json()['detail']


def test_empty_pdf():
    r = client.post('/api/summarize', files={'file': ('bad.pdf', b'', 'application/pdf')})
    assert r.status_code == 400


def test_invalid_pdf():
    r = client.post('/api/summarize', files={'file': ('bad.pdf', b'not a pdf', 'application/pdf')})
    assert r.status_code == 422


def test_oversized():
    r = client.post('/api/summarize', files={'file': ('a.pdf', b'%PDF-' + b'a' * (server.MAX_BYTES + 1), 'application/pdf')})
    assert r.status_code == 413


def test_docx_extraction_and_mock_inference(monkeypatch):
    doc = Document()
    doc.add_paragraph('This is a test research paper about transformers and attention mechanisms. ' * 8)
    f = io.BytesIO(); doc.save(f)
    extracted = extract_document(f.getvalue(), '.docx')
    assert 'attention mechanisms' in extracted.text
    def fake_summarize(_):
        return {'summary': 'A concise abstract.', 'sections': ['A section summary.'], 'chunks': 1, 'model': 'mock-model'}
    monkeypatch.setattr(server.model, 'summarize', fake_summarize)
    r = client.post('/api/summarize', files={'file': ('paper.docx', f.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload['summary'] == 'A concise abstract.'
    assert client.get(payload['download_url']).status_code == 200
    assert 'A section summary.' in client.get(payload['download_url']).text


def test_download_bad_token():
    assert client.get('/api/download/not-valid').status_code == 404
