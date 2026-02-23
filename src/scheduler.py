"""APScheduler-configuratie voor achtergrond synchronisatietaken.

Registreert periodieke sync-taken per AFAS-omgeving.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler = BackgroundScheduler(timezone="Europe/Amsterdam")


def get_scheduler() -> BackgroundScheduler:
    return _scheduler


def start_scheduler(sync_callback, full_sync_callback, config) -> None:
    """Start de achtergrondscheduler met sync-taken.

    Args:
        sync_callback: Functie die een incrementele sync uitvoert (accepteert environment_id)
        full_sync_callback: Functie die een volledige sync uitvoert (accepteert environment_id)
        config: AppConfig instantie
    """
    if _scheduler.running:
        logger.info("Scheduler is al actief")
        return

    for env_cfg in config.environments:
        if not env_cfg.get("enabled", True):
            continue

        env_name = env_cfg.get("name", "Onbekend")
        env_nr = env_cfg.get("environment_nr", "0")
        interval = env_cfg.get("sync_interval_minutes", 15)

        # Incrementele sync op interval
        _scheduler.add_job(
            func=sync_callback,
            trigger=IntervalTrigger(minutes=interval),
            args=[env_nr],
            id=f"incremental_sync_{env_nr}",
            name=f"Incrementele sync: {env_name}",
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(
            "Incrementele sync gepland voor '%s' elke %d minuten", env_name, interval
        )

    # Volledige dagelijkse sync
    full_sync_cron = config.sync.get("full_sync_cron", "0 2 * * *")
    hour, minute = 2, 0
    try:
        parts = full_sync_cron.split()
        minute = int(parts[0])
        hour = int(parts[1])
    except Exception:
        pass

    _scheduler.add_job(
        func=full_sync_callback,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="Europe/Amsterdam"),
        args=[None],  # None = alle omgevingen
        id="full_sync_all",
        name="Volledige dagelijkse sync",
        replace_existing=True,
    )
    logger.info("Volledige dagelijkse sync gepland om %02d:%02d", hour, minute)

    _scheduler.start()
    logger.info("Scheduler gestart")


def stop_scheduler() -> None:
    """Stop de achtergrondscheduler netjes."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler gestopt")
