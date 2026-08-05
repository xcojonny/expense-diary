"""API-Tokens für headless-Clients (iOS-Kurzbefehl)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep, UserDep
from app.schemas import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from app.services import tokens as tokens_service

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("", response_model=list[ApiTokenOut])
async def list_tokens(session: SessionDep, user: UserDep) -> list[object]:
    return list(await tokens_service.list_tokens(session, user_id=user.id))


@router.post("", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(
    session: SessionDep, user: UserDep, payload: ApiTokenCreate
) -> ApiTokenCreated:
    """Token anlegen. Der Klartext steht **nur** in dieser Antwort."""
    token, plaintext = await tokens_service.create_token(
        session, user_id=user.id, name=payload.name
    )
    return ApiTokenCreated(token=ApiTokenOut.model_validate(token), plaintext=plaintext)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(session: SessionDep, user: UserDep, token_id: int) -> None:
    token = await tokens_service.get(session, token_id, user_id=user.id)
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token nicht gefunden.")
    await tokens_service.revoke(session, token)
