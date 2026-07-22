from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BookItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    price: float
    availability: str
    rating: int
    detail_url: str


class PayloadSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: int


class BooksPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_url: str
    user_prompt: str
    items: list[BookItem]
    summary: PayloadSummary
    meta: dict
