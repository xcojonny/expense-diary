from app.domain.upload import EXTENSION, detect_media_type

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8
PDF = b"%PDF-1.7\n" + b"\x00" * 16


def test_detects_supported_types() -> None:
    assert detect_media_type(PNG) == "image/png"
    assert detect_media_type(JPEG) == "image/jpeg"
    assert detect_media_type(WEBP) == "image/webp"
    assert detect_media_type(PDF) == "application/pdf"


def test_rejects_unknown_and_short_input() -> None:
    assert detect_media_type(b"not an image at all") is None
    assert detect_media_type(b"short") is None
    assert detect_media_type(b"") is None


def test_every_allowed_type_has_an_extension() -> None:
    for media_type in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
        assert media_type in EXTENSION
