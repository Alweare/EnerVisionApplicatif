from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.api.schemas import AlertRead
from core.api.service.alert_service import AlertService, SiteNotFoundError
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/backend/alerts", tags=["Alerts"])


@router.get(
    "",
    summary="Liste des alertes",
    description=(
        "Retourne les alertes de la plus récente à la plus ancienne"
    ),
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant",
        }
    },
)
def list_alerts(
    db: Annotated[Session, Depends(get_db)],
    site_id: Annotated[str | None, Query(examples=["SITE001"])] = None,
    since: Annotated[datetime | None, Query(examples=["2026-08-09T00:00:00"])] = None,
    severity: Annotated[list[str] | None, Query(examples=[["high", "critical"]])] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlertRead]:
    service = AlertService(db)
    try:
        return service.list_alerts(
            site_id=site_id,
            since=since,
            severities=severity,
            limit=limit,
            offset=offset,
        )
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
