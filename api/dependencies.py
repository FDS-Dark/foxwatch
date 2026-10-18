import logging

import jwt
from fastapi import Depends, HTTPException, Request, status

from databridge.postgres_databridge import PostgresDatabridge
from engine.postgres_engine import PostgresDBEngine
from services.usgs_ingestion import UsgsCollector
from models.auth import AuthUser
from services.auth import AuthService
from services.bfi import BfiService
from services.usgs_ingestion import UsgsIngestionService
from services.observations import ObservationsService
from services.predictions import PredictionsService
from settings import IngestionSettings, config

logger = logging.getLogger(__name__)

_postgres_engine: PostgresDBEngine | None = None
_postgres_databridge: PostgresDatabridge | None = None
_observations_service: ObservationsService | None = None
_predictions_service: PredictionsService | None = None
_bfi_service: BfiService | None = None
_auth_service: AuthService | None = None
_collector: UsgsCollector | None = None


def get_postgres_engine() -> PostgresDBEngine:
    global _postgres_engine
    if _postgres_engine is None:
        _postgres_engine = PostgresDBEngine()
    return _postgres_engine


def get_postgres_databridge() -> PostgresDatabridge:
    global _postgres_databridge
    if _postgres_databridge is None:
        _postgres_databridge = PostgresDatabridge(get_postgres_engine())
    return _postgres_databridge


def init_collector(settings: IngestionSettings | None = None) -> UsgsCollector:
    global _collector, _observations_service, _predictions_service
    _collector = UsgsCollector(settings or IngestionSettings.from_env())
    _observations_service = None
    _predictions_service = None
    return _collector


def get_collector(request: Request) -> UsgsCollector:
    collector = getattr(request.app.state, "collector", None) or _collector
    if collector is None:
        raise HTTPException(503, "Collector is not initialized")
    return collector


def get_ingestion_service(request: Request) -> UsgsIngestionService:
    return UsgsIngestionService(get_collector(request))


def get_observations_service(request: Request) -> ObservationsService:
    global _observations_service
    if _observations_service is None:
        collector = get_collector(request)
        _observations_service = ObservationsService(
            get_postgres_databridge(), collector.settings.station
        )
    return _observations_service


def get_predictions_service(request: Request) -> PredictionsService:
    global _predictions_service
    if _predictions_service is None:
        _predictions_service = PredictionsService(get_observations_service(request))
    return _predictions_service


def get_bfi_service() -> BfiService:
    global _bfi_service
    if _bfi_service is None:
        _bfi_service = BfiService()
    return _bfi_service


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService(get_postgres_databridge())
    return _auth_service


def _get_signing_key() -> str:
    return config.jwt.secret


async def get_current_user(request: Request) -> AuthUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[len("Bearer ") :]
    try:
        payload = jwt.decode(
            token,
            key=_get_signing_key(),
            algorithms=[config.jwt.algorithm],
            audience=config.jwt.audience,
            issuer=config.jwt.issuer,
            options={"verify_signature": config.jwt.verify_signature},
        )
    except jwt.PyJWTError as e:
        logger.warning("JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    return AuthUser(
        id=payload.get("sub", ""),
        email=payload.get("email"),
        name=payload.get("name"),
        roles=payload.get(config.jwt.roles_claim) or [],
        permissions=payload.get(config.jwt.permissions_claim) or [],
    )


def has_role(role_name: str):
    async def check_role(
        user: AuthUser = Depends(get_current_user),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> bool:
        if role_name in user.roles:
            return True
        if await auth_service.user_has_role(user.id, role_name):
            return True
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have the required role: {role_name}",
        )

    return check_role
