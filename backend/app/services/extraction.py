"""Die Extraktions-Pipeline — verdrahtet Ablage, Parser und Modell.

Wegwahl:

1. **Text-PDF** (digitaler eBon) → `extract_pdf_text` + regelbasierter Parser.
   Kein Modell, keine Kosten. Der Normalfall bei PDFs.
2. **Bild oder gescanntes PDF** → Vision-Modell + JSON-Parser.
3. **Kein Modell konfiguriert** → `needs_review` mit Hinweis, damit manuell
   erfasst werden kann. Die App bleibt benutzbar.

Jeder Fehler landet als `status=failed` samt `error` am Bon — ein kaputter Bon
legt die Queue nicht lahm.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain import extraction as parse
from app.domain.money import unit_price_from_total
from app.integrations import documents
from app.integrations.files import PDF, FileStore
from app.integrations.llm import LlmError, VisionModel
from app.models import Category, LineItem, Receipt, ReceiptStatus
from app.services import items as items_service

log = get_logger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "receipt_extraction.de.txt"

NO_MODEL_HINT = (
    "Kein Vision-Modell konfiguriert (LLM_PROVIDER=none) — Positionen bitte "
    "manuell erfassen oder ein Modell hinterlegen."
)


def load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


@dataclass
class ExtractionOutcome:
    status: ReceiptStatus
    item_count: int
    via: str  # "text" | "vision" | "none"
    error: str | None = None


async def _category_ids_by_name(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(sa.select(Category.name, Category.id))).all()
    return {name.casefold(): cid for name, cid in rows}


async def _persist(
    session: AsyncSession, receipt: Receipt, parsed: parse.ParsedReceipt
) -> int:
    """Geparstes Ergebnis an den Bon schreiben (ersetzt bestehende Positionen)."""
    receipt.store_name = parsed.store_name or receipt.store_name
    receipt.purchased_at = parsed.purchased_at or receipt.purchased_at
    if parsed.total_cents is not None:
        receipt.total_cents = parsed.total_cents
    receipt.currency = parsed.currency or receipt.currency

    # Neu-Extraktion: alte Positionen weg, damit nichts doppelt auftaucht.
    await session.execute(sa.delete(LineItem).where(LineItem.receipt_id == receipt.id))

    categories = await _category_ids_by_name(session)
    for position, parsed_item in enumerate(parsed.items):
        category_name = parsed_item.category or (
            parse.guess_category(parsed_item.name) if parsed_item.kind == "product" else None
        )
        line_item = LineItem(
            receipt_id=receipt.id,
            position=position,
            name=parsed_item.name,
            quantity_milli=parsed_item.quantity_milli,
            unit=parsed_item.unit,
            unit_price_cents=parsed_item.unit_price_cents
            or unit_price_from_total(parsed_item.total_price_cents, parsed_item.quantity_milli),
            total_price_cents=parsed_item.total_price_cents,
            vat_class=parsed_item.vat_class,
            kind=parsed_item.kind,
            category_id=categories.get(category_name.casefold()) if category_name else None,
        )
        session.add(line_item)
        await session.flush()
        await items_service.apply_product_mapping(session, line_item)

    return len(parsed.items)


async def _parse_document(
    data: bytes, media_type: str, *, model: VisionModel, settings: Settings
) -> tuple[parse.ParsedReceipt | None, str, str | None]:
    """`(ergebnis, weg, rohtext)`. `ergebnis=None` = kein Modell verfügbar."""
    if media_type == PDF:
        text = documents.extract_pdf_text(data)
        if text:
            parsed = parse.parse_receipt_text(text)
            if parsed.items:
                return parsed, "text", text
        # Gescanntes PDF: erstes eingebettetes Bild ans Modell.
        image = documents.render_pdf_first_page(data)
        if image is None:
            return parse.ParsedReceipt(confidence="low"), "text", text or None
        data, media_type = image, "image/jpeg"

    if not model.available:
        return None, "none", None

    prepared, prepared_type = documents.prepare_image_for_llm(
        data, max_px=settings.llm_max_image_px
    )
    raw = await model.extract(image=prepared, media_type=prepared_type, prompt=load_prompt())
    if raw is None:
        return None, "none", None
    return parse.parse_receipt_json(raw), "vision", raw


async def process_receipt(
    session: AsyncSession,
    receipt_id: int,
    *,
    settings: Settings,
    file_store: FileStore,
    model: VisionModel,
) -> ExtractionOutcome:
    """Einen Bon extrahieren und das Ergebnis speichern.

    Wirft nicht: jeder Fehler wird am Bon vermerkt und als Ergebnis
    zurückgegeben, damit der Worker weiterlaufen kann.
    """
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        return ExtractionOutcome(ReceiptStatus.FAILED, 0, "none", "Bon nicht gefunden")

    receipt.status = ReceiptStatus.PROCESSING.value
    receipt.error = None
    await session.commit()

    try:
        if not receipt.file_path:
            raise ValueError("Bon hat keine Datei")
        data = await file_store.read(receipt.file_path)
        parsed, via, raw = await _parse_document(
            data, receipt.file_media_type or "", model=model, settings=settings
        )

        if parsed is None:
            receipt.status = ReceiptStatus.NEEDS_REVIEW.value
            receipt.confidence = "low"
            receipt.error = NO_MODEL_HINT
            await session.commit()
            log.info("extraction.no_model", extra={"receipt_id": receipt.id})
            return ExtractionOutcome(ReceiptStatus.NEEDS_REVIEW, 0, "none", NO_MODEL_HINT)

        count = await _persist(session, receipt, parsed)
        confidence, needs_review = parse.reconcile(parsed)
        receipt.confidence = confidence
        receipt.raw_text = raw
        receipt.status = (
            ReceiptStatus.NEEDS_REVIEW.value if needs_review else ReceiptStatus.DONE.value
        )
        receipt.error = None
        await session.commit()

        log.info(
            "extraction.done",
            extra={
                "receipt_id": receipt.id,
                "items": count,
                "via": via,
                "status": receipt.status,
            },
        )
        return ExtractionOutcome(ReceiptStatus(receipt.status), count, via)

    except (LlmError, parse.ExtractionError, ValueError, OSError) as exc:
        await session.rollback()
        message = str(exc)
        receipt = await session.get(Receipt, receipt_id)
        if receipt is not None:
            receipt.status = ReceiptStatus.FAILED.value
            receipt.error = message[:2000]
            await session.commit()
        log.warning("extraction.failed", extra={"receipt_id": receipt_id, "error": message})
        return ExtractionOutcome(ReceiptStatus.FAILED, 0, "none", message)
