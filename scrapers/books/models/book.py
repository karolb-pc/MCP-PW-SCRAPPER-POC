from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    title: str
    price_gbp: float
    rating: int | None
    availability: str
    relative_url: str
    absolute_url: str
