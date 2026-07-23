from io import BytesIO

from app.core.logging import get_logger
from app.domain.upload import detect_media_type

log = get_logger(__name__)


def extract_text(data: bytes) -> str | None:
    """Pull the embedded text out of a digital-receipt PDF (REWE & co. eBons are
    text, not scans). Returns the concatenated page text, or None when there's
    no meaningful text (a scanned PDF) — the caller then tries the image path."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:  # defensive: malformed PDF is an ordinary case
        log.warning("pdf text extraction failed", error=str(exc))
        return None
    return text if len(text) >= 20 else None


def first_page_image(data: bytes) -> tuple[bytes, str] | None:
    """Best-effort: pull the first embedded image out of a (scanned) PDF so it
    can be sent to the vision LLM. Returns (image_bytes, media_type) or None
    when nothing usable is found — the caller then routes to needs_review.

    Most receipt PDFs are single-image scans, so the first embedded image is
    the receipt. We do not rasterize vector PDFs (no renderer dependency).
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        for page in reader.pages:
            for image in page.images:
                media_type = detect_media_type(image.data)
                if media_type and media_type.startswith("image/"):
                    return image.data, media_type
    except Exception as exc:  # defensive: malformed PDF is an ordinary case
        log.warning("pdf image extraction failed", error=str(exc))
    return None
