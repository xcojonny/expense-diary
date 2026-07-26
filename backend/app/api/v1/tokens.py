import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import ApiToken, User
from app.schemas.token import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from app.services import token_service

# Personal API tokens: managed from the browser session. The raw secret is
# returned once on creation and never again.
router = APIRouter(prefix="/me/tokens", tags=["tokens"])


@router.post("", response_model=ApiTokenCreated, status_code=201)
async def create_token(
    data: ApiTokenCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiTokenCreated:
    token, raw = await token_service.create_token(db, user, name=data.name)
    return ApiTokenCreated(
        id=token.id,
        name=token.name,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        token=raw,
    )


@router.get("", response_model=list[ApiTokenOut])
async def list_tokens(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApiToken]:
    return await token_service.list_tokens(db, user)


@router.delete("/{token_id}", status_code=204)
async def revoke_token(
    token_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not await token_service.revoke_token(db, user, token_id):
        raise HTTPException(status_code=404, detail="Token nicht gefunden.")
