from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractExtractor(ABC):
    def __repr__(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def extract(self, *args, **kwargs):
        pass
