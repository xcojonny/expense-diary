import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.domain.extraction import (
    ExtractionError,
    ParsedLineItem,
    ParsedReceipt,
    parse_receipt_json,
    reconcile_confidence,
)
from app.domain.normalize import normalize_name
from app.domain.upload import detect_media_type
from app.integrations.llm import get_vision_llm
from app.integrations.storage.local import get_storage
from app.integrations.storage.pdf import first_page_image
from app.models import Category, Item, LineItem, Receipt, ReceiptStatus
from app.prompts import load_extraction_prompt

log = get_logger(__name__)


async def run_extraction(receipt_id: uuid.UUID) -> None:
    """Full pipeline for one receipt, run in the background (ARQ worker or a
    FastAPI BackgroundTask). Opens its own session — never reuses the request's.

    Sets status processing → done | needs_review | failed. Any real error is
    caught and recorded as ``failed`` so a bad receipt never wedges the worker.
    """
    async with get_sessionmaker()() as session:
        receipt = await session.get(Receipt, receipt_id)
        if receipt is None:
            log.warning("extraction: receipt gone", receipt_id=str(receipt_id))
            return

        receipt.status = ReceiptStatus.processing
        await session.commit()

        try:
            await _extract(session, receipt)
        except Exception as exc:
            await session.rollback()
            fresh = await session.get(Receipt, receipt_id)
            if fresh is not None:
                fresh.status = ReceiptStatus.failed
                fresh.error = str(exc)[:500]
                await session.commit()
            log.warning("extraction failed", receipt_id=str(receipt_id), error=str(exc))


async def _extract(session: AsyncSession, receipt: Receipt) -> None:
    image_bytes = get_storage().read(receipt.image_path)
    media_type = detect_media_type(image_bytes)

    if media_type == "application/pdf":
        extracted = first_page_image(image_bytes)
        if extracted is None:
            # No rasterizable image → can't vision-scan; hand to manual review.
            receipt.status = ReceiptStatus.needs_review
            await session.commit()
            return
        image_bytes, media_type = extracted

    if media_type is None:
        raise ExtractionError("unsupported or unreadable file content")

    prompt = load_extraction_prompt(get_settings().default_locale)
    raw = await get_vision_llm().extract(
        image_bytes=image_bytes, media_type=media_type, prompt=prompt
    )
    if raw is None:
        # No model configured (LLM_PROVIDER=none) → manual entry.
        receipt.status = ReceiptStatus.needs_review
        await session.commit()
        return

    parsed = parse_receipt_json(raw)
    await _apply(session, receipt, parsed, raw)


async def _apply(
    session: AsyncSession, receipt: Receipt, parsed: ParsedReceipt, raw: str
) -> None:
    receipt.raw_ocr_text = raw
    if parsed.store_name:
        receipt.store_name = parsed.store_name
    receipt.purchased_at = parsed.purchased_at
    receipt.total = parsed.total
    receipt.currency = parsed.currency

    # Re-extraction is idempotent: drop previously extracted lines first.
    await session.execute(delete(LineItem).where(LineItem.receipt_id == receipt.id))

    categories = await _category_index(session)
    item_cache: dict[str, Item] = {}

    for parsed_item in parsed.items:
        await _add_line_item(session, receipt, parsed_item, categories, item_cache)

    confidence, needs_review = reconcile_confidence(parsed)
    receipt.confidence = confidence
    receipt.status = ReceiptStatus.needs_review if needs_review else ReceiptStatus.done
    await session.commit()


async def _add_line_item(
    session: AsyncSession,
    receipt: Receipt,
    parsed: ParsedLineItem,
    categories: dict[str, uuid.UUID],
    item_cache: dict[str, Item],
) -> None:
    category_id = categories.get(parsed.category) if parsed.category else None

    line = LineItem(
        receipt_id=receipt.id,
        name=parsed.name,
        quantity=parsed.quantity,
        unit=parsed.unit,
        unit_price=parsed.unit_price,
        total_price=parsed.total_price,
        vat_class=parsed.vat_class,
        line_type=parsed.line_type,
        category_id=category_id,
    )

    # Only real products anchor to an Item (the trend key). Deposit/discount
    # lines are receipt-local and carry no normalized name.
    if parsed.line_type == "product":
        normalized = normalize_name(parsed.name)
        if normalized:
            line.normalized_name = normalized
            item = await _resolve_item(
                session, receipt.group_id, normalized, parsed.name, category_id, item_cache
            )
            line.item_id = item.id
            if category_id is not None and item.category_id is None:
                item.category_id = category_id

    session.add(line)


async def _resolve_item(
    session: AsyncSession,
    group_id: uuid.UUID,
    normalized: str,
    display_name: str,
    category_id: uuid.UUID | None,
    cache: dict[str, Item],
) -> Item:
    if normalized in cache:
        return cache[normalized]
    item = (
        await session.execute(
            select(Item).where(Item.group_id == group_id, Item.normalized_name == normalized)
        )
    ).scalar_one_or_none()
    if item is None:
        item = Item(
            group_id=group_id,
            normalized_name=normalized,
            display_name=display_name,
            category_id=category_id,
        )
        session.add(item)
        await session.flush()  # need item.id for the line FK
    cache[normalized] = item
    return item


async def _category_index(session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = (await session.execute(select(Category.name, Category.id))).all()
    return {name: cid for name, cid in rows}
