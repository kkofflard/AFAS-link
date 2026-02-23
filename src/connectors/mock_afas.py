"""Mock AFAS-connector voor demo- en testdoeleinden.

Geeft realistische nep-medewerkergegevens terug zonder echte AFAS-verbinding.
"""
import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DUTCH_FIRST_NAMES = [
    "Jan", "Piet", "Klaas", "Henk", "Erik", "Maarten", "Thomas", "Wouter",
    "Jeroen", "Bas", "Sander", "Roel", "Mark", "Tim", "Frank", "Stefan",
    "Maria", "Anne", "Lisa", "Emma", "Petra", "Ingrid", "Marieke", "Sandra",
    "Carla", "Miriam", "Jolanda", "Esther", "Nicole", "Iris", "Laura", "Chantal",
]
DUTCH_LAST_NAMES = [
    "de Vries", "van den Berg", "Janssen", "de Boer", "Visser", "Smit", "Meijer",
    "de Groot", "Bos", "Mulder", "Peters", "van Dijk", "Bakker", "Hendriks",
    "Kuiper", "Laan", "Dekker", "Brouwer", "de Jong", "van der Berg",
    "Oosterhout", "Vermeulen", "van Leeuwen", "Willems", "de Wit", "Schouten",
]
DEPARTMENTS = ["ICT", "HR", "Finance", "Marketing", "Operations", "Sales", "Juridisch", "Inkoop"]
FUNCTIONS = {
    "ICT": ["Systeembeheerder", "Ontwikkelaar", "IT-manager", "Servicedesk medewerker"],
    "HR": ["HR-adviseur", "Recruiter", "HR-manager", "Salarisadministrateur"],
    "Finance": ["Controller", "Boekhouder", "CFO", "Financial analyst"],
    "Marketing": ["Marketeer", "Content specialist", "Marketing manager"],
    "Operations": ["Operationeel manager", "Logistiek medewerker", "Planner"],
    "Sales": ["Accountmanager", "Verkoopbinnendienst", "Sales director"],
    "Juridisch": ["Jurist", "Compliance officer", "Legal counsel"],
    "Inkoop": ["Inkoper", "Inkoopmanager", "Procurement specialist"],
}
TEAMS = ["Team Noord", "Team Zuid", "Team Oost", "Team West", "Centraal team"]


def _generate_initials(first_name: str) -> str:
    """Genereer initialen vanuit voornaam."""
    parts = first_name.split()
    return "".join(p[0].upper() + "." for p in parts)


def _fake_employee(emp_id: int, start_months_ago: int = 12, is_leaving: bool = False) -> dict:
    """Genereer een realistisch nep-medewerkerrecord."""
    first_name = random.choice(DUTCH_FIRST_NAMES)
    last_name = random.choice(DUTCH_LAST_NAMES)
    department = random.choice(DEPARTMENTS)
    function = random.choice(FUNCTIONS[department])
    team = random.choice(TEAMS)

    start_date = date.today() - timedelta(days=start_months_ago * 30)
    end_date = None
    if is_leaving:
        end_date = date.today() + timedelta(days=random.randint(-5, 30))

    return {
        "EmId": str(100 + emp_id),
        "VoornaamVolledig": first_name,
        "Initialen": _generate_initials(first_name),
        "Nm": last_name,
        "FunctionDescription": function,
        "DepartmentDescription": department,
        "TeamDescription": team,
        "CostCenterDescription": f"KP-{department[:3].upper()}-{random.randint(100, 999)}",
        "StartDate": start_date.isoformat(),
        "EndDate": end_date.isoformat() if end_date else None,
        "Mutatiedatum": (datetime.utcnow() - timedelta(hours=random.randint(0, 72))).isoformat(),
    }


# Vaste dataset voor reproduceerbaarheid in demo-modus
_DEMO_EMPLOYEES: list[dict] = []


def _build_demo_employees() -> list[dict]:
    random.seed(42)
    employees = []
    # 20 actieve medewerkers
    for i in range(20):
        employees.append(_fake_employee(i + 1, start_months_ago=random.randint(1, 36)))
    # 3 uitdienstgetreden medewerkers
    for i in range(3):
        employees.append(_fake_employee(100 + i + 1, start_months_ago=24, is_leaving=True))
    return employees


class MockAfasConnector:
    """Mock AFAS-connector die nep-medewerkergegevens retourneert."""

    def __init__(self, environment_nr: str = "DEMO", **kwargs):
        self.environment_nr = environment_nr
        global _DEMO_EMPLOYEES
        if not _DEMO_EMPLOYEES:
            _DEMO_EMPLOYEES = _build_demo_employees()

    def get_employees(
        self,
        modified_since: Optional[datetime] = None,
        skip: int = 0,
        take: int = 100,
    ) -> list[dict]:
        employees = _DEMO_EMPLOYEES.copy()
        if modified_since:
            employees = [
                e for e in employees
                if datetime.fromisoformat(e["Mutatiedatum"]) >= modified_since
            ]
        result = employees[skip:skip + take]
        logger.info(
            "Mock AFAS: %d medewerkers teruggegeven (skip=%d, take=%d)",
            len(result), skip, take
        )
        return result

    def test_connection(self) -> bool:
        logger.info("Mock AFAS verbindingstest geslaagd")
        return True
