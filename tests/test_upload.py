import pytest

from app.ingestion import upload
from app.core.errors import PipelineError


def test_magic_bytes_not_extension():
    assert upload.sniff_kind(b"%PDF-1.7 ...") == "pdf"
    assert upload.sniff_kind(b"\x89PNG\r\n\x1a\n....") == "png"
    assert upload.sniff_kind(b"\xff\xd8\xff\xe0....") == "jpg"
    assert upload.sniff_kind(b"MZ\x90\x00 an exe renamed to .pdf") is None


def test_store_random_name_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(upload.config, "UPLOAD_DIR", tmp_path)
    s = upload.store(b"%PDF-1.4 fake")
    assert s.path.parent == tmp_path and len(s.file_id) == 32 and s.path.suffix == ".pdf"
    s.delete()
    assert not s.path.exists()


def test_rejects_bad_type_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr(upload.config, "UPLOAD_DIR", tmp_path)
    with pytest.raises(PipelineError) as e:
        upload.store(b"hello")
    assert e.value.error_class == "upload_bad_type"
    monkeypatch.setattr(upload.config, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(PipelineError) as e:
        upload.store(b"%PDF-" + b"x" * 20)
    assert e.value.error_class == "upload_too_large"
