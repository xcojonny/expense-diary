import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.upload import EXTENSION
from app.integrations.storage.local import get_storage
from app.models import Receipt, ReceiptStatus


async def create_receipt(
    session: AsyncSession, *, group_id: uuid.UUID, data: bytes, media_type: str
) -> Receipt:
    """Persist the uploaded file and create a receipt in status ``uploaded``.
    The caller schedules extraction after this returns."""
    path = get_storage().save(data, EXTENSION[media_type])
    receipt = Receipt(group_id=group_id, image_path=path, status=ReceiptStatus.uploaded)
    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)
    return receipt
