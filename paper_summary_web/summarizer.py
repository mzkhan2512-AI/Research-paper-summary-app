"""PDF/DOCX extraction and hierarchical Transformer summarization."""
from __future__ import annotations

import io
import threading
import zipfile
from dataclasses import dataclass

MAX_CHARS = 150_000
MAX_PAGES = 150
MAX_CHUNKS = 45
MODEL_NAME = "sshleifer/distilbart-cnn-12-6"


class UserFacingError(Exception):
    """An error suitable for display to the person uploading the document."""


@dataclass
class Extracted:
    text: str
    units: int
    kind: str


def extract_document(data: bytes, extension: str) -> Extracted:
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise UserFacingError("This file is not a valid PDF. Please upload an unencrypted PDF.")
        try:
            import fitz
            with fitz.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise UserFacingError("Password-protected PDFs are not supported.")
                if len(doc) > MAX_PAGES:
                    raise UserFacingError(f"This PDF exceeds the {MAX_PAGES}-page limit.")
                pages = []
                for page in doc:
                    pages.append(page.get_text("text", sort=True))
                text = "\n".join(pages)
                units = len(doc)
        except UserFacingError:
            raise
        except Exception as exc:
            raise UserFacingError("This PDF could not be read. It may be damaged or encrypted.") from exc
    elif extension == ".docx":
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise UserFacingError("This file is not a valid Word .docx document.")
        try:
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text.strip() for cell in row.cells))
            text = "\n".join(parts)
            units = len(doc.paragraphs)
        except Exception as exc:
            raise UserFacingError("This Word file could not be read. Try saving it again as .docx.") from exc
    else:
        raise UserFacingError("Only PDF (.pdf) and Word (.docx) files are accepted.")

    if not text.strip() or len(text.split()) < 45:
        raise UserFacingError("Not enough extractable text was found. Scanned PDFs need OCR, which this version does not support.")
    if len(text) > MAX_CHARS:
        raise UserFacingError(f"This document is too long ({len(text):,} characters). Maximum is {MAX_CHARS:,} characters.")
    return Extracted(text=" ".join(text.split()), units=units, kind=extension.lstrip("."))


class TransformerSummarizer:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model = None
        self._device = None

    def load(self):
        with self._lock:
            if self._model is not None:
                return
            try:
                import torch
                from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                model.to(device).eval()
            except Exception as exc:
                raise UserFacingError(
                    "The AI model could not load. Check your internet connection for the first download, "
                    "available memory, and installed dependencies. See the server logs."
                ) from exc
            self._tokenizer, self._model, self._device = tokenizer, model, device

    def _chunks(self, text: str, max_tokens: int = 850) -> list[str]:
        ids = self._tokenizer.encode(text, add_special_tokens=False)
        return [self._tokenizer.decode(ids[i:i + max_tokens], skip_special_tokens=True)
                for i in range(0, len(ids), max_tokens)]

    def _generate(self, text: str, max_new_tokens: int = 140) -> str:
        import torch
        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=1000)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.inference_mode():
            outputs = self._model.generate(
                **inputs, max_new_tokens=max_new_tokens, min_new_tokens=25,
                num_beams=4, do_sample=False, early_stopping=True,
            )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    def summarize(self, text: str) -> dict:
        self.load()
        chunks = self._chunks(text)
        if len(chunks) > MAX_CHUNKS:
            raise UserFacingError(f"This document requires {len(chunks)} chunks; the current safe limit is {MAX_CHUNKS}.")
        partial = [self._generate(chunk) for chunk in chunks]
        consolidated = " ".join(partial)
        # Compress iteratively to preserve cross-section material without truncating the entire document.
        for _ in range(5):
            groups = self._chunks(consolidated)
            if len(groups) == 1:
                break
            consolidated = " ".join(self._generate(group, 180) for group in groups)
        if len(self._chunks(consolidated)) > 1:
            raise UserFacingError("The document could not be consolidated within the model's input limit.")
        overview = self._generate(consolidated, 220) if len(partial) > 1 else partial[0]
        return {"summary": overview, "sections": partial, "chunks": len(chunks), "model": self.model_name}
