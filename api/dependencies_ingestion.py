"""Optional shared-secret guard for manual ingestion triggers."""

from __future__ import annotations

from fastapi import Header, HTTPException

import settings


def require_ingestion_admin(
    x_ingestion_token: str | None = Header(default=None, alias="X-Ingestion-Token"),
) -> None:
    token = settings.INGESTION_ADMIN_TOKEN
    if not token:
        return
    if x_ingestion_token != token:
        raise HTTPException(status_code=401, detail="Invalid or missing ingestion admin token")
