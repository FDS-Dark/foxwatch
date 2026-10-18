from sqlalchemy.engine import URL as SQL_ALCHEMY_URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from structlog import get_logger

from engine.base_engine import BaseEngine
from settings import config, resolved_database_url

logger = get_logger()


class PostgresDBEngine(BaseEngine):
    def __init__(self) -> None:
        super().__init__(self.create_engine())

    def create_engine(self) -> AsyncEngine:
        url = self._make_url()
        if isinstance(url, str):
            url = make_url(url)
        if url.drivername in ("postgresql", "postgres"):
            url = url.set(drivername="postgresql+asyncpg")
        logger.info("Creating Postgres database engine", host=url.host, database=url.database)
        return create_async_engine(url, pool_pre_ping=True)

    def _make_url(self) -> SQL_ALCHEMY_URL | str:
        url = resolved_database_url()
        if url:
            return url
        cfg = config.database
        return SQL_ALCHEMY_URL.create(
            drivername="postgresql+asyncpg",
            database=cfg.name,
            username=cfg.username,
            password=cfg.password,
            host=cfg.host,
            port=cfg.port,
            query={"ssl": cfg.ssl} if cfg.ssl != "disable" else {},
        )
