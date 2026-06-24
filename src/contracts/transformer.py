from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractTransformer(ABC):
    def __repr__(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def transform(self, *args, **kwargs):
        pass
