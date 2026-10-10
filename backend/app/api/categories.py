from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nama: str
    keyword: str


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Annotated[Session, Depends(get_db)]):
    return db.scalars(select(Category).order_by(Category.nama)).all()
