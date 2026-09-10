from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.api.schemas import AlertRead
from core.api.service.alert_service import AlertService, SiteNotFoundError
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/backend/alerts", tags=["Alerts"])

#test
@router.get(
    "",
    response_model=list[AlertRead],
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
    site_id: str | None = Query(default=None, examples=["SITE001"]),
    since: datetime | None = Query(default=None, examples=["2026-08-09T00:00:00"]),
    severity: list[str] | None = Query(default=None, examples=[["high", "critical"]]),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
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
