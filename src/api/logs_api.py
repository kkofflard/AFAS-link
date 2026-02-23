"""REST API-routes voor synchronisatielogs."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import SyncLog, SyncStatus, SyncAction

router = APIRouter(prefix="/api")


@router.get("/logs")
def list_logs(
    page: int = 1,
    per_page: int = 30,
    status: Optional[str] = None,
    action: Optional[str] = None,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Haal gepagineerde synchronisatielogs op."""
    query = db.query(SyncLog)

    if status:
        try:
            query = query.filter(SyncLog.status == SyncStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ongeldige status: {status}")

    if action:
        try:
            query = query.filter(SyncLog.action == SyncAction(action))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ongeldige actie: {action}")

    if employee_id:
        query = query.filter(SyncLog.employee_id == employee_id)

    total = query.count()
    logs = (
        query.order_by(SyncLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "totaal": total,
        "pagina": page,
        "per_pagina": per_page,
        "logs": [
            {
                "id": log.id,
                "tijdstempel": log.timestamp.isoformat(),
                "medewerker_id": log.employee_id,
                "actie": log.action.value,
                "doel": log.target.value,
                "status": log.status.value,
                "bericht": log.message,
                "details": log.details,
            }
            for log in logs
        ],
    }
