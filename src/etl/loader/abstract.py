from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractLoader(ABC):
    def __repr__(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def load(self, *args, **kwargs):
        pass
