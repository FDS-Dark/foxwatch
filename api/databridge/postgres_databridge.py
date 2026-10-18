from typing import Any

import pandas as pd
from structlog import get_logger

from databridge.base_databridge import ThreadpoolAsyncDatabridge
from engine.postgres_engine import PostgresDBEngine

logger = get_logger()


class PostgresDatabridge(ThreadpoolAsyncDatabridge):
    def __init__(self, engine: PostgresDBEngine) -> None:
        super().__init__(engine)

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        try:
            data, columns = await self.query_procedure_safe_async(query, params)
            return pd.DataFrame(data, columns=columns)
        except Exception as e:
            logger.error("Error executing custom query", error=str(e))
            raise
