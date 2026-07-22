from __future__ import annotations

from typing import Any


class BaseETL:
    """Config-driven ETL orchestrator.

    Concrete scrapers pass a ``CONFIG`` dict of the shape::

        {
            "extractor":   {"_class": <Extractor>,   "params": {...}},
            "transformer": {"_class": <Transformer>, "params": {...}},
            "validator":   {"_class": <Validator>},          # optional
            "loader":      {"_class": <Loader>,      "params": {...}},
        }

    and subclass this class to implement ``extract`` / ``transform`` /
    ``validate`` / ``load`` and a ``run`` that chains them.
    """

    def __init__(self, config: dict[str, Any]):
        self.extractor = self.__build_instance(**config.get("extractor"))
        self.transformer = self.__build_instance(**config.get("transformer"))
        self.validator = self.__build_instance(**config.get("validator", {"_class": None}))
        self.loader = self.__build_instance(**config.get("loader"))

    def __repr__(self) -> str:
        return self.__class__.__name__

    @staticmethod
    def __build_instance(_class, params=None):
        if _class is None:
            return None
        if params is not None:
            return _class(**params)
        return _class()

    def extract(self, *args, **kwargs):
        raise NotImplementedError

    def transform(self, *args, **kwargs):
        raise NotImplementedError

    def validate(self, *args, **kwargs):
        raise NotImplementedError

    def load(self, *args, **kwargs):
        raise NotImplementedError
