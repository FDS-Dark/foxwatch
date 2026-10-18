from abc import ABC, abstractmethod

from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL as SQL_ALCHEMY_URL
from sqlalchemy.ext.asyncio import AsyncEngine


class BaseEngine(ABC):
    def __init__(self, engine: Engine | AsyncEngine) -> None:
        self.engine: Engine | AsyncEngine = engine

    @abstractmethod
    def create_engine(self) -> Engine | AsyncEngine:
        pass

    @abstractmethod
    def _make_url(self) -> SQL_ALCHEMY_URL | str:
        pass
