"""REST API-routes voor medewerkersbeheer."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Employee, EmployeeStatus

router = APIRouter(prefix="/api")


@router.get("/medewerkers")
def list_employees(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Haal een gepagineerde lijst van medewerkers op."""
    query = db.query(Employee)

    if status:
        try:
            query = query.filter(Employee.status == EmployeeStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ongeldige status: {status}")

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

    return {
        "totaal": total,
        "pagina": page,
        "per_pagina": per_page,
        "medewerkers": [_employee_to_dict(e) for e in employees],
    }


@router.get("/medewerkers/{employee_id}")
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    """Haal details van één medewerker op, inclusief synchronisatiehistorie."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Medewerker niet gevonden")

    recent_logs = (
        employee.sync_logs
        .order_by("timestamp desc")
        .limit(20)
        .all()
    )

    return {
        **_employee_to_dict(employee),
        "synchronisatiehistorie": [
            {
                "id": log.id,
                "tijdstempel": log.timestamp.isoformat(),
                "actie": log.action.value,
                "doel": log.target.value,
                "status": log.status.value,
                "bericht": log.message,
            }
            for log in recent_logs
        ],
    }


def _employee_to_dict(e: Employee) -> dict:
    return {
        "id": e.id,
        "afas_id": e.afas_employee_id,
        "voornaam": e.first_name,
        "initialen": e.initials,
        "achternaam": e.last_name,
        "weergavenaam": e.display_name,
        "functie": e.function,
        "afdeling": e.department,
        "team": e.team,
        "email": e.generated_email,
        "gebruikersnaam": e.generated_username,
        "status": e.status.value if e.status else None,
        "heeft_entra_id": e.has_entra_id,
        "heeft_ad": e.has_ad,
        "startdatum": e.start_date.isoformat() if e.start_date else None,
        "einddatum": e.end_date.isoformat() if e.end_date else None,
        "laatste_sync": e.last_synced_at.isoformat() if e.last_synced_at else None,
    }
