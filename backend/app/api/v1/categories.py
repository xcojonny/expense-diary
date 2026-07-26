import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Category
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import category_service
from app.services.category_service import CategoryError

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.sort_order, Category.name))
    return list(result.scalars().all())


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    data: CategoryCreate, db: AsyncSession = Depends(get_db)
) -> Category:
    try:
        return await category_service.create_category(db, data)
    except CategoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _get_category(db: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden.")
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID, data: CategoryUpdate, db: AsyncSession = Depends(get_db)
) -> Category:
    category = await _get_category(db, category_id)
    try:
        return await category_service.update_category(db, category, data)
    except CategoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    category = await _get_category(db, category_id)
    await category_service.delete_category(db, category)
