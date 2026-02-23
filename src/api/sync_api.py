"""REST API-routes voor synchronisatie-beheer."""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import AfasEnvironment, SyncLog, SyncStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Globale sync-status (eenvoudige in-memory status)
_sync_status = {
    "running": False,
    "last_started": None,
    "last_completed": None,
    "last_stats": None,
}


def get_sync_status() -> dict:
    return _sync_status


async def _run_sync_task(env_id: Optional[int] = None):
    """Voer sync uit in de achtergrond."""
    from src.database import SessionLocal
    from src.main import create_sync_engine_for_env

    _sync_status["running"] = True
    _sync_status["last_started"] = datetime.utcnow().isoformat()

    db = SessionLocal()
    try:
        if env_id:
            env = db.query(AfasEnvironment).filter(AfasEnvironment.id == env_id).first()
            environments = [env] if env else []
        else:
            environments = db.query(AfasEnvironment).filter(AfasEnvironment.enabled == True).all()

        total_stats = {"provisioned": 0, "updated": 0, "deprovisioned": 0, "errors": 0}
        for env in environments:
            try:
                engine = create_sync_engine_for_env(db, env)
                stats = engine.run_incremental_sync()
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)
            except Exception as e:
                logger.error("Sync mislukt voor omgeving %s: %s", env.name, e)
                total_stats["errors"] += 1

        _sync_status["last_stats"] = total_stats
        _sync_status["last_completed"] = datetime.utcnow().isoformat()
    finally:
        db.close()
        _sync_status["running"] = False


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Statuscheck voor de applicatie en database."""
    try:
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "verbonden" if db_ok else "fout",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/sync/trigger")
async def trigger_sync(background_tasks: BackgroundTasks, env_id: Optional[int] = None):
    """Start een handmatige synchronisatie in de achtergrond."""
    if _sync_status["running"]:
        raise HTTPException(status_code=409, detail="Er loopt al een synchronisatie")

    background_tasks.add_task(_run_sync_task, env_id)
    return {
        "status": "gestart",
        "message": "Synchronisatie is gestart",
        "environment_id": env_id,
    }


@router.get("/sync/status")
def sync_status():
    """Haal de huidige synchronisatiestatus op."""
    return {
        "actief": _sync_status["running"],
        "laatste_start": _sync_status["last_started"],
        "laatste_voltooid": _sync_status["last_completed"],
        "laatste_statistieken": _sync_status["last_stats"],
    }


@router.get("/sync/environments")
def list_environments(db: Session = Depends(get_db)):
    """Lijst van geconfigureerde AFAS-omgevingen."""
    environments = db.query(AfasEnvironment).all()
    return [
        {
            "id": env.id,
            "naam": env.name,
            "omgeving_nr": env.environment_nr,
            "ingeschakeld": env.enabled,
            "sync_interval_minuten": env.sync_interval_minutes,
            "laatste_incrementele_sync": env.last_incremental_sync_at.isoformat() if env.last_incremental_sync_at else None,
            "laatste_volledige_sync": env.last_full_sync_at.isoformat() if env.last_full_sync_at else None,
        }
        for env in environments
    ]
