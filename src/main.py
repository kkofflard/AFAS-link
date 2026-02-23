"""AFAS-link hoofdapplicatie.

FastAPI-applicatie voor de AFAS–Entra ID/Active Directory koppeling.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.config import config
from src.database import create_tables, SessionLocal
from src.models import AfasEnvironment

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_sync_engine_for_env(db: Session, env: AfasEnvironment):
    """Maak een SyncEngine aan voor een specifieke AFAS-omgeving."""
    from src.engines.sync_engine import SyncEngine
    from src.engines.naming_engine import NamingEngine
    from src.engines.mapping_engine import MappingEngine

    demo_mode = config.demo_mode
    entra_cfg = config.entra_id
    ad_cfg = config.active_directory

    # Selecteer de juiste connectors (mock of echt)
    if demo_mode:
        from src.connectors.mock_afas import MockAfasConnector
        from src.connectors.mock_entra_id import MockEntraIdConnector
        from src.connectors.mock_ad import MockActiveDirectoryConnector
        afas_conn = MockAfasConnector(environment_nr=env.environment_nr)
        entra_conn = MockEntraIdConnector(domain=entra_cfg.get("domain", "demo.nl"))
        ad_conn = MockActiveDirectoryConnector() if ad_cfg.get("enabled") else None
    else:
        from src.connectors.afas import AfasConnector
        from src.connectors.entra_id import EntraIdConnector
        from src.connectors.active_directory import ActiveDirectoryConnector

        token = config.get_afas_token(env.token_env_var)
        if not token:
            raise RuntimeError(f"Geen AFAS-token gevonden voor omgeving '{env.name}' (env var: {env.token_env_var})")

        afas_conn = AfasConnector(
            environment_nr=env.environment_nr,
            token=token,
            connector_id=env.afas_connector_id,
        )
        entra_conn = EntraIdConnector(
            tenant_id=entra_cfg.get("tenant_id", ""),
            client_id=entra_cfg.get("client_id", ""),
            client_secret=entra_cfg.get("client_secret", ""),
            domain=entra_cfg.get("domain", ""),
        )
        ad_conn = None
        if ad_cfg.get("enabled"):
            bind_password = os.getenv(ad_cfg.get("bind_password_env_var", "AD_BIND_PASSWORD"), "")
            ad_conn = ActiveDirectoryConnector(
                server=ad_cfg.get("server", ""),
                base_dn=ad_cfg.get("base_dn", ""),
                bind_user=ad_cfg.get("bind_user", ""),
                bind_password=bind_password,
                port=ad_cfg.get("port", 636),
                use_ssl=ad_cfg.get("use_ssl", True),
                disabled_ou=ad_cfg.get("disabled_ou"),
            )

    naming_cfg = config.naming
    naming_engine = NamingEngine(
        domain=entra_cfg.get("domain", "demo.nl"),
        pattern=naming_cfg.get("pattern", "{initials}.{lastname}@{domain}"),
        fallback_patterns=naming_cfg.get("fallback_patterns"),
        username_pattern=naming_cfg.get("username_pattern", "{initials}.{lastname}"),
    )
    mapping_engine = MappingEngine(
        attribute_mapping=config.attribute_mapping,
        group_mappings=config.group_mappings,
        ou_mappings=config.ou_mappings,
    )

    licenses = [lic["sku_id"] for lic in entra_cfg.get("licenses", [])]

    return SyncEngine(
        db=db,
        afas_connector=afas_conn,
        entra_connector=entra_conn,
        ad_connector=ad_conn,
        naming_engine=naming_engine,
        mapping_engine=mapping_engine,
        environment=env,
        enable_ad=ad_cfg.get("enabled", False) and ad_conn is not None,
        license_sku_ids=licenses,
    )


def _ensure_demo_environments(db: Session) -> None:
    """Zorg dat er minimaal één AFAS-omgeving in de database staat (voor demo)."""
    existing = db.query(AfasEnvironment).count()
    if existing == 0:
        env_configs = config.environments
        if env_configs:
            for env_cfg in env_configs:
                env = AfasEnvironment(
                    name=env_cfg.get("name", "Demo omgeving"),
                    environment_nr=env_cfg.get("environment_nr", "00000"),
                    token_env_var=env_cfg.get("token_env_var", "AFAS_ENV1_TOKEN"),
                    afas_connector_id=env_cfg.get("afas_connector_id", "HrPersonContact"),
                    enabled=env_cfg.get("enabled", True),
                    sync_interval_minutes=env_cfg.get("sync_interval_minutes", 15),
                )
                db.add(env)
        else:
            # Standaard demo-omgeving als geen config aanwezig is
            db.add(AfasEnvironment(
                name="Demo Omgeving",
                environment_nr="00000",
                token_env_var="AFAS_ENV1_TOKEN",
                enabled=True,
                sync_interval_minutes=15,
            ))
        db.commit()
        logger.info("Demo AFAS-omgeving aangemaakt in de database")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Applicatie levenscyclus: startup en shutdown."""
    # Startup
    logger.info("AFAS-link opgestart (demo_mode=%s)", config.demo_mode)
    create_tables()

    db = SessionLocal()
    try:
        _ensure_demo_environments(db)
    finally:
        db.close()

    # Scheduler starten
    try:
        from src.scheduler import start_scheduler

        def incremental_sync_callback(env_nr: str):
            db = SessionLocal()
            try:
                env = db.query(AfasEnvironment).filter(
                    AfasEnvironment.environment_nr == env_nr
                ).first()
                if env:
                    engine = create_sync_engine_for_env(db, env)
                    engine.run_incremental_sync()
            except Exception as e:
                logger.error("Geplande incrementele sync mislukt voor %s: %s", env_nr, e)
            finally:
                db.close()

        def full_sync_callback(env_nr: Optional[str]):
            db = SessionLocal()
            try:
                if env_nr:
                    envs = [db.query(AfasEnvironment).filter(
                        AfasEnvironment.environment_nr == env_nr
                    ).first()]
                else:
                    envs = db.query(AfasEnvironment).filter(AfasEnvironment.enabled == True).all()

                for env in envs:
                    if env:
                        engine = create_sync_engine_for_env(db, env)
                        engine.run_full_sync()
            except Exception as e:
                logger.error("Geplande volledige sync mislukt: %s", e)
            finally:
                db.close()

        start_scheduler(incremental_sync_callback, full_sync_callback, config)
    except Exception as e:
        logger.warning("Scheduler kon niet worden gestart: %s", e)

    yield

    # Shutdown
    try:
        from src.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    logger.info("AFAS-link afgesloten")


# FastAPI applicatie aanmaken
app = FastAPI(
    title="AFAS-link",
    description="Automatische koppeling tussen AFAS en Microsoft Entra ID / Active Directory",
    version="1.0.0",
    lifespan=lifespan,
)

# Statische bestanden
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Routes registreren
from src.api.dashboard import router as dashboard_router
from src.api.sync_api import router as sync_router
from src.api.employees_api import router as employees_router
from src.api.logs_api import router as logs_router

app.include_router(dashboard_router)
app.include_router(sync_router)
app.include_router(employees_router)
app.include_router(logs_router)


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse(url="/static/favicon.ico", status_code=302)
