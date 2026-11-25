from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes import chat, documents, settings, system
from app.core.security import require_api_key

api_router = APIRouter()
# Health probes stay unauthenticated so orchestrators can reach them.
api_router.include_router(system.health_router)

protected = [Depends(require_api_key)]
api_router.include_router(system.stats_router)
api_router.include_router(documents.router, dependencies=protected)
api_router.include_router(chat.router, dependencies=protected)
api_router.include_router(settings.router, dependencies=protected)
