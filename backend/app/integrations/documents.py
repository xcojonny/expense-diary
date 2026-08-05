"""PDF- und Bildvorbereitung — die einzige Stelle mit pypdf/Pillow.

Zwei Aufgaben:

* **Text aus PDFs ziehen.** Digitale eBons sind Text-PDFs; ihr Inhalt geht
  direkt in den LLM-freien Parser (`domain/extraction.parse_receipt_text`).
* **Bilder für das Modell aufbereiten.** Ein Handyfoto hat 12 MP; die
  Verkleinerung auf `LLM_MAX_IMAGE_PX` spart Tokens und Zeit, ohne dass ein Bon
  unleserlich wird. HEIC (iPhone-Standard) wird dabei zu JPEG, weil die meisten
  Vision-APIs HEIC nicht annehmen.
"""

from __future__ import annotations

import io

from app.core.logging import get_logger

log = get_logger(__name__)

# HEIC braucht ein zusätzliches Plugin. Fehlt es, funktioniert alles andere
# weiter — nur HEIC-Fotos können dann nicht ans Modell gehen.
try:  # pragma: no cover - abhängig von der Installation
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:  # pragma: no cover
    HEIC_SUPPORTED = False


def extract_pdf_text(data: bytes) -> str:
    """Eingebetteten Text eines PDFs zurückgeben (leer bei einem Scan)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:  # kaputtes PDF darf die Extraktion nicht abbrechen
        log.warning("pdf.text_failed", extra={"error": str(exc)})
        return ""


def render_pdf_first_page(data: bytes) -> bytes | None:
    """Erstes eingebettetes Bild eines gescannten PDFs.

    Bewusst *kein* Rasterizer (kein poppler/pdf2image): gescannte Bons bestehen
    aus genau einem eingebetteten Bild pro Seite, und das lässt sich ohne
    Systemabhängigkeit herausholen.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            for image in page.images:
                if image.data:
                    return bytes(image.data)
    except Exception as exc:
        log.warning("pdf.image_failed", extra={"error": str(exc)})
    return None


def prepare_image_for_llm(data: bytes, *, max_px: int) -> tuple[bytes, str]:
    """`(bytes, media_type)` — verkleinertes JPEG für den Vision-Adapter.

    Gelingt die Umwandlung nicht, geht das Original raus: ein Modell, das das
    Format doch versteht, ist besser als ein harter Fehler.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as opened:
            # EXIF-Rotation anwenden — ein hochkant fotografierter Bon liegt
            # sonst quer und wird schlechter gelesen.
            picture = ImageOps.exif_transpose(opened) or opened
            if picture.mode not in ("RGB", "L"):
                picture = picture.convert("RGB")
            if max(picture.size) > max_px:
                picture.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            picture.save(buffer, format="JPEG", quality=85, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception as exc:
        log.warning("image.prepare_failed", extra={"error": str(exc)})
        return data, "image/jpeg"
