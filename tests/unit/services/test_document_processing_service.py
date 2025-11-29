"""Unit tests for DocumentProcessingService."""

from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from core.services.document_processing_service import DocumentProcessingService


class DummyPDF:
    """Context manager stub for pdfplumber.open."""

    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyPage:
    def __init__(self, text: str | None):
        self._text = text

    def extract_text(self):
        return self._text


def _install_mock_module(monkeypatch, name: str, module):
    """Helper to inject a dummy module into sys.modules."""
    monkeypatch.setitem(sys.modules, name, module)


def test_process_pdf_success(monkeypatch):
    service = DocumentProcessingService()
    dummy_module = SimpleNamespace(open=lambda _: DummyPDF([DummyPage("Hello"), DummyPage("World")]))
    _install_mock_module(monkeypatch, "pdfplumber", dummy_module)

    success, markdown, content_hash, error = service.process_document(b"%PDF", "file.pdf", "pdf")

    assert success is True
    assert error is None
    assert "Hello" in markdown
    assert "World" in markdown
    assert content_hash is not None


def test_process_pdf_no_text_fallback(monkeypatch):
    service = DocumentProcessingService()
    dummy_module = SimpleNamespace(open=lambda _: DummyPDF([DummyPage(None)]))
    _install_mock_module(monkeypatch, "pdfplumber", dummy_module)

    success, markdown, _, error = service.process_document(b"%PDF", "file.pdf", "pdf")

    assert success is True
    assert error is None
    assert "_В PDF не обнаружен текстовый слой" in markdown


def test_process_txt_success():
    service = DocumentProcessingService()
    payload = "Sample text file\nwith multiple lines".encode("utf-8")

    success, markdown, _, error = service.process_document(payload, "notes.txt", "txt")

    assert success is True
    assert error is None
    assert "Sample text file" in markdown
    assert markdown.startswith("```\n")


def test_process_txt_fallback_encoding():
    service = DocumentProcessingService()
    payload = "Café".encode("latin-1")

    success, markdown, _, error = service.process_document(payload, "notes.txt", "txt")

    assert success is True
    assert error is None
    assert "Café" in markdown


def test_process_csv_success(monkeypatch):
    service = DocumentProcessingService()
    csv_data = "col1,col2\n1,2\n3,4".encode("utf-8")

    def fake_to_markdown(self, *args, **kwargs):
        return "| col1 | col2 |\n| 1 | 2 |"

    monkeypatch.setattr(pd.DataFrame, "to_markdown", fake_to_markdown, raising=False)
    monkeypatch.setitem(sys.modules, "pandas", pd)

    success, markdown, _, error = service.process_document(csv_data, "data.csv", "csv")

    assert success is True
    assert error is None
    assert "| col1 | col2 |" in markdown


def test_process_excel_success(monkeypatch):
    service = DocumentProcessingService()
    df = pd.DataFrame({"name": ["Alice"], "age": [30]})

    def fake_read_excel(_):
        return df

    def fake_to_markdown(self, *args, **kwargs):
        return "| name | age |\n| Alice | 30 |"

    monkeypatch.setattr(pd.DataFrame, "to_markdown", fake_to_markdown, raising=False)
    monkeypatch.setitem(sys.modules, "pandas", pd)

    dummy_module = SimpleNamespace(read_excel=fake_read_excel, read_csv=pd.read_csv)
    _install_mock_module(monkeypatch, "pandas", dummy_module)

    success, markdown, _, error = service.process_document(b"bytes", "people.xlsx", "excel")

    assert success is True
    assert error is None
    assert "Alice" in markdown


def test_process_spreadsheet_markdown_failure(monkeypatch):
    service = DocumentProcessingService()

    class BadFrame(pd.DataFrame):
        def to_markdown(self, *args, **kwargs):
            raise ValueError("tabulate missing")

    def fake_read_csv(_):
        return BadFrame({"x": [1]})

    dummy_module = SimpleNamespace(read_csv=fake_read_csv, read_excel=pd.read_excel)
    _install_mock_module(monkeypatch, "pandas", dummy_module)

    success, markdown, _, error = service.process_document(b"csv", "data.csv", "csv")

    assert success is False
    assert markdown is None
    assert "tabulate" in error.lower()


def test_process_word_success(monkeypatch):
    service = DocumentProcessingService()

    class DummyParagraph:
        def __init__(self, text):
            self.text = text

    class DummyCell:
        def __init__(self, text):
            self.text = text

    class DummyRow:
        def __init__(self, cells):
            self.cells = [DummyCell(value) for value in cells]

    class DummyTable:
        def __init__(self, rows):
            self.rows = [DummyRow(row) for row in rows]

    class DummyDocument:
        paragraphs = [DummyParagraph("Paragraph one."), DummyParagraph("Paragraph two.")]
        tables = [DummyTable([["Name", "Role"], ["Alice", "Engineer"]])]

    dummy_module = SimpleNamespace(Document=lambda _: DummyDocument())
    _install_mock_module(monkeypatch, "docx", dummy_module)

    success, markdown, _, error = service.process_document(b"doc-bytes", "report.docx", "word")

    assert success is True
    assert error is None
    assert "Paragraph one." in markdown
    assert "Alice | Engineer" in markdown


def test_process_word_no_text(monkeypatch):
    service = DocumentProcessingService()

    class EmptyParagraph:
        def __init__(self, text):
            self.text = text

    class EmptyDocument:
        paragraphs = [EmptyParagraph("   "), EmptyParagraph("")]
        tables = []

    dummy_module = SimpleNamespace(Document=lambda _: EmptyDocument())
    _install_mock_module(monkeypatch, "docx", dummy_module)

    success, markdown, _, error = service.process_document(b"", "empty.docx", "word")

    assert success is False
    assert markdown is None
    assert "No text content" in error


def test_process_document_unsupported_type():
    service = DocumentProcessingService()

    success, markdown, content_hash, error = service.process_document(b"data", "archive.zip", "other")

    assert success is False
    assert markdown is None
    assert content_hash is None
    assert "Unsupported document type" in error


def test_process_document_exception(monkeypatch):
    service = DocumentProcessingService()

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_process_pdf", explode)

    success, markdown, content_hash, error = service.process_document(b"%PDF", "file.pdf", "pdf")

    assert success is False
    assert markdown is None
    assert content_hash is None
    assert "boom" in error


def test_process_pdf_error(monkeypatch):
    service = DocumentProcessingService()

    def failing_open(_):
        raise RuntimeError("pdf failure")

    dummy_module = SimpleNamespace(open=failing_open)
    _install_mock_module(monkeypatch, "pdfplumber", dummy_module)

    success, markdown, _, error = service.process_document(b"%PDF", "file.pdf", "pdf")

    assert success is False
    assert markdown is None
    assert "pdf failure" in error.lower()


def test_detect_document_type():
    service = DocumentProcessingService()

    assert service.detect_document_type("file.PDF") == "pdf"
    assert service.detect_document_type("spreadsheet.xlsx") == "excel"
    assert service.detect_document_type("notes.txt") == "txt"
    assert service.detect_document_type("unknown.bin") == "other"
