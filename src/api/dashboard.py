"""HTML-routes voor het Nederlandstalige dashboard."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta

from src.database import get_db
from src.models import Employee, EmployeeStatus, SyncLog, SyncStatus, AfasEnvironment

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # Statistieken
    total_employees = db.query(func.count(Employee.id)).scalar()
    active_employees = db.query(func.count(Employee.id)).filter(
        Employee.status == EmployeeStatus.ACTIVE
    ).scalar()
    disabled_employees = db.query(func.count(Employee.id)).filter(
        Employee.status == EmployeeStatus.DISABLED
    ).scalar()
    error_employees = db.query(func.count(Employee.id)).filter(
        Employee.status == EmployeeStatus.ERROR
    ).scalar()

    # Recente logs (laatste 10)
    recent_logs = (
        db.query(SyncLog)
        .order_by(SyncLog.timestamp.desc())
        .limit(10)
        .all()
    )

    # Omgevingen
    environments = db.query(AfasEnvironment).all()

    # Fouten afgelopen 24 uur
    since_24h = datetime.utcnow() - timedelta(hours=24)
    errors_24h = db.query(func.count(SyncLog.id)).filter(
        SyncLog.status == SyncStatus.ERROR,
        SyncLog.timestamp >= since_24h,
    ).scalar()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_employees": total_employees,
        "active_employees": active_employees,
        "disabled_employees": disabled_employees,
        "error_employees": error_employees,
        "errors_24h": errors_24h,
        "recent_logs": recent_logs,
        "environments": environments,
        "now": datetime.utcnow(),
    })


@router.get("/medewerkers", response_class=HTMLResponse)
def employees_page(
    request: Request,
    page: int = 1,
    status: str = "",
    search: str = "",
    db: Session = Depends(get_db),
):
    per_page = 20
    query = db.query(Employee)

    if status:
        try:
            query = query.filter(Employee.status == EmployeeStatus(status))
        except ValueError:
            pass
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Employee.first_name.ilike(search_term))
            | (Employee.last_name.ilike(search_term))
            | (Employee.generated_email.ilike(search_term))
            | (Employee.department.ilike(search_term))
        )

    total = query.count()
    employees = (
        query.order_by(Employee.last_name, Employee.first_name)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return templates.TemplateResponse("employees.html", {
        "request": request,
        "employees": employees,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "status_filter": status,
        "search": search,
        "statuses": [s.value for s in EmployeeStatus],
    })


@router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    page: int = 1,
    status: str = "",
    action: str = "",
    db: Session = Depends(get_db),
):
    from src.models import SyncAction, SyncTarget
    per_page = 30
    query = db.query(SyncLog)

    if status:
        try:
            query = query.filter(SyncLog.status == SyncStatus(status))
        except ValueError:
            pass
    if action:
        try:
            query = query.filter(SyncLog.action == SyncAction(action))
        except ValueError:
            pass

    total = query.count()
    logs = (
        query.order_by(SyncLog.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    from src.models import SyncAction, SyncTarget
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "logs": logs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "status_filter": status,
        "action_filter": action,
        "statuses": [s.value for s in SyncStatus],
        "actions": [a.value for a in SyncAction],
    })
