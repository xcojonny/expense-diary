"""Kategorienverwaltung."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep, UserDep
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import categories as categories_service

router = APIRouter(prefix="/categories", tags=["categories"])


async def _load(session: SessionDep, category_id: int) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Kategorie nicht gefunden."
        )
    return category


@router.get("", response_model=list[CategoryOut])
async def list_categories(session: SessionDep, _user: UserDep) -> list[Category]:
    return await categories_service.list_all(session)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    session: SessionDep, _user: UserDep, payload: CategoryCreate
) -> Category:
    try:
        return await categories_service.create(
            session,
            name=payload.name,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_food=payload.is_food,
        )
    except categories_service.CategoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    session: SessionDep, _user: UserDep, category_id: int, payload: CategoryUpdate
) -> Category:
    category = await _load(session, category_id)
    try:
        return await categories_service.update(
            session,
            category,
            name=payload.name,
            parent_id=payload.parent_id,
            clear_parent=payload.clear_parent,
            sort_order=payload.sort_order,
            is_food=payload.is_food,
        )
    except categories_service.CategoryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(session: SessionDep, _user: UserDep, category_id: int) -> None:
    """Löschen nimmt keine Daten mit: Unterkategorien werden zu Top-Level,
    Positions- und Artikelverweise auf `NULL` (FK `SET NULL`)."""
    category = await _load(session, category_id)
    await categories_service.delete(session, category)
