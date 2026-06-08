"""Unit tests pentru app/core/uploads.py — utilitar de upload imagini."""
from __future__ import annotations

import io

import pytest


class _FakeUpload:
    """Mock UploadFile (content_type + filename + file BytesIO)."""

    def __init__(self, content_type: str, filename: str, content: bytes):
        self.content_type = content_type
        self.filename = filename
        self.file = io.BytesIO(content)


def _png_bytes() -> bytes:
    """Header PNG minimal valid."""
    return b"\x89PNG\r\n\x1a\n" + b"x" * 50


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"x" * 50


# ---------------------------------------------------------------------------
# Validare content_type + erori
# ---------------------------------------------------------------------------

class TestSaveUploadedImageValidation:

    def test_rejects_unsupported_content_type(self, tmp_path):
        from fastapi import HTTPException
        from app.core.uploads import save_uploaded_image
        with pytest.raises(HTTPException) as exc:
            save_uploaded_image(
                _FakeUpload("image/gif", "test.gif", _png_bytes()),
                tmp_path,
            )
        assert exc.value.status_code == 400

    def test_rejects_oversized_file(self, tmp_path):
        from fastapi import HTTPException
        from app.core.uploads import save_uploaded_image, MAX_PHOTO_SIZE_BYTES
        big_content = _png_bytes() + b"y" * (MAX_PHOTO_SIZE_BYTES + 100)
        with pytest.raises(HTTPException) as exc:
            save_uploaded_image(
                _FakeUpload("image/png", "big.png", big_content),
                tmp_path,
            )
        assert exc.value.status_code in (400, 413)


# ---------------------------------------------------------------------------
# Save successful cases
# ---------------------------------------------------------------------------

class TestSaveSuccess:

    def test_saves_png_returns_string_path(self, tmp_path):
        from app.core.uploads import save_uploaded_image
        content = _png_bytes()
        result = save_uploaded_image(
            _FakeUpload("image/png", "photo.png", content),
            tmp_path,
        )
        # Result e string (cale relativa sau absoluta)
        assert isinstance(result, str)
        assert len(result) > 0
        # Verific fisierul exista efectiv (cautam in tmp_path)
        from pathlib import Path
        files = list(tmp_path.glob("**/*.png"))
        assert len(files) >= 1
        assert files[0].read_bytes() == content

    def test_saves_jpeg(self, tmp_path):
        from app.core.uploads import save_uploaded_image
        result = save_uploaded_image(
            _FakeUpload("image/jpeg", "photo.jpg", _jpeg_bytes()),
            tmp_path,
        )
        assert isinstance(result, str)
        from pathlib import Path
        files = list(tmp_path.glob("**/*"))
        # Cel putin un fisier creat
        non_dir = [f for f in files if f.is_file()]
        assert len(non_dir) >= 1

    def test_creates_directory_if_missing(self, tmp_path):
        """Daca destination directory nu exista, e creat (mkdir parents)."""
        from app.core.uploads import save_uploaded_image
        sub = tmp_path / "uploads" / "photos"
        assert not sub.exists()
        save_uploaded_image(
            _FakeUpload("image/png", "p.png", _png_bytes()),
            sub,
        )
        assert sub.exists()

    def test_uses_custom_prefix(self, tmp_path):
        """Prefix se aplica in numele fisierului salvat."""
        from app.core.uploads import save_uploaded_image
        save_uploaded_image(
            _FakeUpload("image/png", "x.png", _png_bytes()),
            tmp_path,
            prefix="profile",
        )
        # Caut fisier care contine "profile" in nume
        files = list(tmp_path.glob("profile*.png"))
        assert len(files) >= 1, f"Expected file starting with 'profile', got {list(tmp_path.iterdir())}"
