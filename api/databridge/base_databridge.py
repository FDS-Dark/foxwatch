import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine, Row
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog import get_logger

from engine.base_engine import BaseEngine

logger = get_logger()


class ThreadpoolAsyncDatabridge:
    def __init__(self, engine: BaseEngine) -> None:
        self.engine: BaseEngine = engine
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def query_procedure_safe_async(
        self, query: str, params: dict[str, Any] | None = None
    ) -> tuple[Sequence[Row], list[str]]:
        if isinstance(self.engine.engine, AsyncEngine):
            return await self._execute_query_async(query, params or {})
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._execute_query_sync, query, params or {}
        )

    async def _execute_query_async(
        self, query: str, params: dict[str, Any]
    ) -> tuple[Sequence[Row], list[str]]:
        try:
            async with self.engine.engine.begin() as conn:  # type: ignore[union-attr]
                result = await conn.execute(text(query), params)
                data = result.fetchall()
                columns = [str(key) for key in result.keys()]
                return data, columns
        except Exception as e:
            logger.info("Error executing async query", error=str(e))
            raise

    def _execute_query_sync(
        self, query: str, params: dict[str, Any]
    ) -> tuple[Sequence[Row], list[str]]:
        try:
            if isinstance(self.engine.engine, Engine):
                conn = self.engine.engine.connect()
                result = conn.execute(text(query), params)
                data = result.fetchall()
                columns = [str(key) for key in result.keys()]
                conn.close()
                return data, columns
            raise ValueError("Engine is not a sync engine")
        except Exception as e:
            logger.info("Error executing sync query", error=str(e))
            raise
