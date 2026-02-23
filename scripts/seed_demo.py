#!/usr/bin/env python3
"""Demo-seeder voor AFAS-link.

Vult de database met realistische Nederlandse nep-medewerkers en
historische synchronisatielogs zodat het dashboard direct werkt
zonder echte AFAS- of Entra ID-credentials.

Gebruik:
    python scripts/seed_demo.py
"""
import os
import sys
import random
from datetime import datetime, date, timedelta
from pathlib import Path

# Voeg de projectroot toe aan het Python-pad
sys.path.insert(0, str(Path(__file__).parent.parent))

# Zet demo-modus aan voor de seed
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./afas_link.db")
os.environ.setdefault("CONFIG_PATH", "config/config.yaml")

from src.database import create_tables, SessionLocal
from src.models import (
    Employee, EmployeeStatus, SyncLog, SyncAction, SyncTarget, SyncStatus,
    AfasEnvironment,
)

# Configuratiebestanden aanmaken als ze niet bestaan
config_dir = Path("config")
config_dir.mkdir(exist_ok=True)

config_yaml = config_dir / "config.yaml"
if not config_yaml.exists():
    import shutil
    example = config_dir / "config.example.yaml"
    if example.exists():
        shutil.copy(example, config_yaml)
    else:
        config_yaml.write_text("""environments:
  - name: "Demo Omgeving"
    environment_nr: "00000"
    token_env_var: "AFAS_ENV1_TOKEN"
    enabled: true
    sync_interval_minutes: 15
    afas_connector_id: "HrPersonContact"

entra_id:
  domain: "demo-bedrijf.nl"

active_directory:
  enabled: false

naming:
  pattern: "{initials}.{lastname}@{domain}"
  fallback_patterns:
    - "{initials}.{lastname}{n}@{domain}"
    - "{firstname}.{lastname}@{domain}"

sync:
  full_sync_cron: "0 2 * * *"
""")

mappings_yaml = config_dir / "mappings.yaml"
if not mappings_yaml.exists():
    mappings_example = config_dir / "mappings.example.yaml"
    if mappings_example.exists():
        import shutil
        shutil.copy(mappings_example, mappings_yaml)
    else:
        mappings_yaml.write_text("""attribute_mapping:
  - afas_field: "EmId"
    internal_field: "afas_employee_id"
  - afas_field: "VoornaamVolledig"
    internal_field: "first_name"
  - afas_field: "Initialen"
    internal_field: "initials"
  - afas_field: "Nm"
    internal_field: "last_name"
  - afas_field: "FunctionDescription"
    internal_field: "function"
  - afas_field: "DepartmentDescription"
    internal_field: "department"
  - afas_field: "StartDate"
    internal_field: "start_date"
    transform: date_iso
  - afas_field: "EndDate"
    internal_field: "end_date"
    transform: date_iso

group_mappings: []
ou_mappings: []
""")

# Nederlandse demo-gegevens
FIRST_NAMES_M = ["Jan", "Piet", "Henk", "Erik", "Maarten", "Thomas", "Wouter",
                  "Jeroen", "Bas", "Sander", "Roel", "Mark", "Tim", "Frank", "Stefan"]
FIRST_NAMES_F = ["Maria", "Anne", "Lisa", "Emma", "Petra", "Ingrid", "Marieke",
                  "Sandra", "Carla", "Miriam", "Jolanda", "Esther", "Nicole", "Iris"]
LAST_NAMES = [
    ("de Vries", "devries"), ("van den Berg", "vdberg"), ("Janssen", "janssen"),
    ("de Boer", "deboer"), ("Visser", "visser"), ("Smit", "smit"), ("Meijer", "meijer"),
    ("de Groot", "degroot"), ("Bos", "bos"), ("Mulder", "mulder"),
    ("Peters", "peters"), ("van Dijk", "vandijk"), ("Bakker", "bakker"),
    ("Hendriks", "hendriks"), ("Dekker", "dekker"), ("Brouwer", "brouwer"),
    ("de Jong", "dejong"), ("Willems", "willems"), ("de Wit", "dewit"),
    ("Schouten", "schouten"), ("Oosterhout", "oosterhout"), ("Vermeulen", "vermeulen"),
]
DEPARTMENTS = ["ICT", "HR", "Finance", "Marketing", "Operations", "Sales", "Juridisch", "Inkoop"]
FUNCTIONS = {
    "ICT": ["Systeembeheerder", "Softwareontwikkelaar", "IT-manager", "Servicedesk medewerker", "Netwerkbeheerder"],
    "HR": ["HR-adviseur", "Recruiter", "HR-manager", "Salarisadministrateur", "HR-medewerker"],
    "Finance": ["Controller", "Boekhouder", "CFO", "Financial analyst", "Crediteur administratie"],
    "Marketing": ["Marketeer", "Content specialist", "Marketing manager", "SEO specialist"],
    "Operations": ["Operationeel manager", "Logistiek medewerker", "Planner", "Magazijnmedewerker"],
    "Sales": ["Accountmanager", "Verkoopbinnendienst", "Sales director", "Key account manager"],
    "Juridisch": ["Jurist", "Compliance officer", "Legal counsel", "Paralegal"],
    "Inkoop": ["Inkoper", "Inkoopmanager", "Procurement specialist", "Category manager"],
}
DOMAIN = "demo-bedrijf.nl"


def generate_email(initials: str, last_name_clean: str, existing: set) -> str:
    candidate = f"{initials}.{last_name_clean}@{DOMAIN}"
    if candidate not in existing:
        return candidate
    for n in range(2, 20):
        candidate = f"{initials}.{last_name_clean}{n}@{DOMAIN}"
        if candidate not in existing:
            return candidate
    return f"{initials}.{last_name_clean}.{random.randint(100,999)}@{DOMAIN}"


def seed():
    print("AFAS-link demo-seeder")
    print("=" * 40)

    create_tables()
    db = SessionLocal()
    random.seed(2024)

    try:
        # Verwijder bestaande data
        db.query(SyncLog).delete()
        db.query(Employee).delete()
        db.query(AfasEnvironment).delete()
        db.commit()
        print("Bestaande data gewist.")

        # Demo-omgeving aanmaken
        env = AfasEnvironment(
            name="Demo Omgeving BV",
            environment_nr="00000",
            token_env_var="AFAS_ENV1_TOKEN",
            enabled=True,
            sync_interval_minutes=15,
            last_incremental_sync_at=datetime.utcnow() - timedelta(minutes=8),
            last_full_sync_at=datetime.utcnow() - timedelta(hours=6),
        )
        db.add(env)
        db.flush()

        used_emails = set()
        employees = []
        all_names = [(n, "m") for n in FIRST_NAMES_M] + [(n, "f") for n in FIRST_NAMES_F]
        random.shuffle(all_names)

        # 20 actieve medewerkers aanmaken
        print("\nAanmaken van 20 actieve medewerkers...")
        for i in range(20):
            first_name, gender = all_names[i % len(all_names)]
            last_name_full, last_name_clean = random.choice(LAST_NAMES)
            department = random.choice(DEPARTMENTS)
            function = random.choice(FUNCTIONS[department])

            initials = first_name[0].lower()
            email = generate_email(initials, last_name_clean, used_emails)
            used_emails.add(email)
            username = email.split("@")[0]

            start_date = date.today() - timedelta(days=random.randint(30, 1200))
            emp = Employee(
                afas_employee_id=str(100 + i + 1),
                afas_environment_id=env.id,
                first_name=first_name,
                initials=first_name[0].upper() + ".",
                last_name=last_name_full,
                display_name=f"{first_name} {last_name_full}",
                function=function,
                department=department,
                team=f"Team {random.choice(['Noord', 'Zuid', 'Oost', 'West', 'Centraal'])}",
                cost_center=f"KP-{department[:3].upper()}-{random.randint(100, 999)}",
                start_date=start_date,
                generated_email=email,
                generated_username=username,
                entra_id_object_id=f"entra-{100 + i + 1:04d}-demo",
                status=EmployeeStatus.ACTIVE,
                last_synced_at=datetime.utcnow() - timedelta(hours=random.randint(0, 48)),
            )
            db.add(emp)
            db.flush()
            employees.append(emp)

            # Provisioning log aanmaken
            prov_time = emp.last_synced_at or datetime.utcnow()
            db.add(SyncLog(
                employee_id=emp.id,
                afas_environment_id=env.id,
                action=SyncAction.PROVISION,
                target=SyncTarget.ENTRA_ID,
                status=SyncStatus.SUCCESS,
                message=f"Entra ID-account aangemaakt: {email}",
                timestamp=prov_time,
                details={"email": email, "department": department},
            ))
            db.add(SyncLog(
                employee_id=emp.id,
                afas_environment_id=env.id,
                action=SyncAction.GROUP_ASSIGN,
                target=SyncTarget.ENTRA_ID,
                status=SyncStatus.SUCCESS,
                message=f"Groep GRP-{department} toegewezen",
                timestamp=prov_time + timedelta(seconds=2),
            ))
            print(f"  ✓ {emp.display_name} ({email})")

        # 3 uitdienstgetreden medewerkers aanmaken
        print("\nAanmaken van 3 uitdienstgetreden medewerkers...")
        for i in range(3):
            first_name, _ = all_names[(20 + i) % len(all_names)]
            last_name_full, last_name_clean = random.choice(LAST_NAMES)
            department = random.choice(DEPARTMENTS)

            initials = first_name[0].lower()
            email = generate_email(initials, last_name_clean, used_emails)
            used_emails.add(email)
            username = email.split("@")[0]

            end_date = date.today() - timedelta(days=random.randint(1, 30))
            emp = Employee(
                afas_employee_id=str(200 + i + 1),
                afas_environment_id=env.id,
                first_name=first_name,
                initials=first_name[0].upper() + ".",
                last_name=last_name_full,
                display_name=f"{first_name} {last_name_full}",
                function=random.choice(FUNCTIONS[department]),
                department=department,
                start_date=date.today() - timedelta(days=random.randint(365, 900)),
                end_date=end_date,
                generated_email=email,
                generated_username=username,
                entra_id_object_id=f"entra-{200 + i + 1:04d}-demo",
                status=EmployeeStatus.DISABLED,
                last_synced_at=datetime.utcnow() - timedelta(days=random.randint(1, 5)),
            )
            db.add(emp)
            db.flush()

            deprov_time = emp.last_synced_at or datetime.utcnow()
            for action, msg in [
                (SyncAction.LICENSE_REVOKE, "Alle licenties ingetrokken"),
                (SyncAction.GROUP_REMOVE, "Verwijderd uit alle groepen"),
                (SyncAction.DEPROVISION, "Entra ID-account uitgeschakeld"),
            ]:
                db.add(SyncLog(
                    employee_id=emp.id,
                    afas_environment_id=env.id,
                    action=action,
                    target=SyncTarget.ENTRA_ID,
                    status=SyncStatus.SUCCESS,
                    message=msg,
                    timestamp=deprov_time,
                ))
            print(f"  ✓ {emp.display_name} (uitdienstgetreden)")

        # 1 medewerker met fout
        first_name, _ = all_names[23 % len(all_names)]
        last_name_full = "Foutman"
        err_emp = Employee(
            afas_employee_id="999",
            afas_environment_id=env.id,
            first_name=first_name,
            last_name=last_name_full,
            display_name=f"{first_name} {last_name_full}",
            function="Onbekend",
            department="HR",
            start_date=date.today() - timedelta(days=5),
            status=EmployeeStatus.ERROR,
        )
        db.add(err_emp)
        db.flush()
        db.add(SyncLog(
            employee_id=err_emp.id,
            afas_environment_id=env.id,
            action=SyncAction.PROVISION,
            target=SyncTarget.ENTRA_ID,
            status=SyncStatus.ERROR,
            message="Entra ID provisioning mislukt: Licentie niet beschikbaar",
            timestamp=datetime.utcnow() - timedelta(hours=2),
        ))

        # Systeem sync-logs aanmaken
        print("\nAanmaken van systeem sync-logs...")
        for hours_ago in [0, 1, 6, 12, 24]:
            ts = datetime.utcnow() - timedelta(hours=hours_ago)
            db.add(SyncLog(
                afas_environment_id=env.id,
                action=SyncAction.SYNC_START,
                target=SyncTarget.SYSTEM,
                status=SyncStatus.INFO,
                message=f"Incrementele sync gestart voor omgeving Demo Omgeving BV",
                timestamp=ts,
            ))
            db.add(SyncLog(
                afas_environment_id=env.id,
                action=SyncAction.SYNC_COMPLETE,
                target=SyncTarget.SYSTEM,
                status=SyncStatus.SUCCESS,
                message="Sync voltooid: 0 nieuw, 2 bijgewerkt, 0 uitgeschakeld, 0 fouten",
                timestamp=ts + timedelta(seconds=45),
            ))

        db.commit()

        # Samenvatting
        total_emp = db.query(Employee).count()
        total_logs = db.query(SyncLog).count()
        print(f"\n{'=' * 40}")
        print(f"Seed voltooid!")
        print(f"  Medewerkers: {total_emp}")
        print(f"  Sync-logs:   {total_logs}")
        print(f"{'=' * 40}")
        print(f"\nStart de applicatie met:")
        print(f"  uvicorn src.main:app --reload")
        print(f"\nOpen het dashboard op: http://localhost:8000")

    except Exception as e:
        db.rollback()
        print(f"\nFout tijdens seeden: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
