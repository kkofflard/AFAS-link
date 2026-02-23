"""Synchronisatie-engine die de volledige provisioning-levenscyclus orkestreert.

Verwerkt AFAS-mutaties en voert provisioning, updates en deprovisioning uit
in Entra ID en/of Active Directory.
"""
import logging
from datetime import datetime, date
from typing import Optional, Any
from sqlalchemy.orm import Session

from src.models import Employee, EmployeeStatus, SyncLog, SyncAction, SyncTarget, SyncStatus, AfasEnvironment
from src.engines.naming_engine import NamingEngine
from src.engines.mapping_engine import MappingEngine
from src.config import config

logger = logging.getLogger(__name__)


class SyncEngine:
    """Orkestreert de volledige AFAS → Entra ID / Active Directory synchronisatiecyclus."""

    def __init__(
        self,
        db: Session,
        afas_connector,
        entra_connector,
        ad_connector,
        naming_engine: NamingEngine,
        mapping_engine: MappingEngine,
        environment: AfasEnvironment,
        enable_ad: bool = False,
        license_sku_ids: Optional[list[str]] = None,
    ):
        self.db = db
        self.afas = afas_connector
        self.entra = entra_connector
        self.ad = ad_connector
        self.naming = naming_engine
        self.mapping = mapping_engine
        self.environment = environment
        self.enable_ad = enable_ad
        self.license_sku_ids = license_sku_ids or []

    def _log(
        self,
        action: SyncAction,
        target: SyncTarget,
        status: SyncStatus,
        message: str,
        employee: Optional[Employee] = None,
        details: Optional[dict] = None,
    ) -> SyncLog:
        entry = SyncLog(
            employee_id=employee.id if employee else None,
            afas_environment_id=self.environment.id,
            action=action,
            target=target,
            status=status,
            message=message,
            details=details,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def _get_existing_emails(self) -> set[str]:
        """Haal alle gegenereerde e-mailadressen op uit de lokale database."""
        rows = self.db.query(Employee.generated_email).filter(
            Employee.generated_email.isnot(None)
        ).all()
        return {row[0].lower() for row in rows}

    def run_incremental_sync(self) -> dict:
        """Voer een incrementele synchronisatie uit (alleen gewijzigde medewerkers)."""
        last_sync = self.environment.last_incremental_sync_at
        logger.info(
            "Start incrementele sync voor omgeving '%s' (gewijzigd na: %s)",
            self.environment.name, last_sync
        )
        self._log(
            SyncAction.SYNC_START, SyncTarget.SYSTEM, SyncStatus.INFO,
            f"Incrementele sync gestart voor omgeving {self.environment.name}"
        )
        self.db.commit()

        employees = self.afas.get_employees(modified_since=last_sync)
        stats = self._process_employees(employees)

        self.environment.last_incremental_sync_at = datetime.utcnow()
        self._log(
            SyncAction.SYNC_COMPLETE, SyncTarget.SYSTEM, SyncStatus.SUCCESS,
            f"Incrementele sync voltooid: {stats['provisioned']} nieuw, {stats['updated']} bijgewerkt, "
            f"{stats['deprovisioned']} uitgeschakeld, {stats['errors']} fouten"
        )
        self.db.commit()
        logger.info("Incrementele sync klaar: %s", stats)
        return stats

    def run_full_sync(self) -> dict:
        """Voer een volledige synchronisatie uit (alle medewerkers)."""
        logger.info("Start volledige sync voor omgeving '%s'", self.environment.name)
        self._log(
            SyncAction.SYNC_START, SyncTarget.SYSTEM, SyncStatus.INFO,
            f"Volledige sync gestart voor omgeving {self.environment.name}"
        )
        self.db.commit()

        employees = self.afas.get_employees(modified_since=None)
        stats = self._process_employees(employees)

        self.environment.last_full_sync_at = datetime.utcnow()
        self.environment.last_incremental_sync_at = datetime.utcnow()
        self._log(
            SyncAction.SYNC_COMPLETE, SyncTarget.SYSTEM, SyncStatus.SUCCESS,
            f"Volledige sync voltooid: {stats['provisioned']} nieuw, {stats['updated']} bijgewerkt, "
            f"{stats['deprovisioned']} uitgeschakeld, {stats['errors']} fouten"
        )
        self.db.commit()
        logger.info("Volledige sync klaar: %s", stats)
        return stats

    def _process_employees(self, afas_records: list[dict]) -> dict:
        """Verwerk een lijst van AFAS-medewerkerrecords."""
        stats = {"provisioned": 0, "updated": 0, "deprovisioned": 0, "errors": 0, "skipped": 0}

        for record in afas_records:
            try:
                attrs = self.mapping.map_employee(record)
                afas_id = str(attrs.get("afas_employee_id", ""))
                if not afas_id:
                    logger.warning("AFAS-record zonder medewerker-ID overgeslagen: %s", record)
                    stats["skipped"] += 1
                    continue

                employee = self.db.query(Employee).filter(
                    Employee.afas_employee_id == afas_id,
                    Employee.afas_environment_id == self.environment.id,
                ).first()

                end_date = attrs.get("end_date")
                is_leaving = (
                    end_date is not None
                    and isinstance(end_date, date)
                    and end_date <= date.today()
                )

                if employee is None:
                    # Nieuwe medewerker
                    employee = self._create_employee_record(afas_id, attrs)
                    if is_leaving:
                        logger.info("Medewerker %s direct uit dienst, overslaan", afas_id)
                        stats["skipped"] += 1
                        continue
                    self._provision(employee, attrs)
                    stats["provisioned"] += 1
                else:
                    # Bestaande medewerker
                    self._update_employee_record(employee, attrs)
                    if is_leaving and employee.status == EmployeeStatus.ACTIVE:
                        self._deprovision(employee, attrs)
                        stats["deprovisioned"] += 1
                    elif not is_leaving and employee.status == EmployeeStatus.ACTIVE:
                        self._update_provisioned_user(employee, attrs)
                        stats["updated"] += 1

                self.db.commit()

            except Exception as e:
                logger.error("Fout bij verwerken AFAS-record %s: %s", record.get("EmId"), e, exc_info=True)
                stats["errors"] += 1
                self.db.rollback()

        return stats

    def _create_employee_record(self, afas_id: str, attrs: dict) -> Employee:
        """Maak een nieuw Employee-record aan in de database."""
        employee = Employee(
            afas_employee_id=afas_id,
            afas_environment_id=self.environment.id,
            status=EmployeeStatus.PENDING,
        )
        self._apply_attrs(employee, attrs)
        self.db.add(employee)
        self.db.flush()
        return employee

    def _update_employee_record(self, employee: Employee, attrs: dict) -> None:
        """Werk een bestaand Employee-record bij met nieuwe AFAS-waarden."""
        self._apply_attrs(employee, attrs)

    @staticmethod
    def _apply_attrs(employee: Employee, attrs: dict) -> None:
        """Kopieer gemapte attributen naar een Employee-object."""
        field_map = {
            "first_name": "first_name",
            "initials": "initials",
            "last_name": "last_name",
            "function": "function",
            "department": "department",
            "team": "team",
            "cost_center": "cost_center",
            "start_date": "start_date",
            "end_date": "end_date",
        }
        for attr_key, model_field in field_map.items():
            if attr_key in attrs:
                setattr(employee, model_field, attrs[attr_key])

        # Genereer weergavenaam
        parts = [p for p in [employee.first_name, employee.last_name] if p]
        if parts:
            employee.display_name = " ".join(parts)

    def _provision(self, employee: Employee, attrs: dict) -> None:
        """Provisioneer een nieuwe medewerker in Entra ID en optioneel AD."""
        logger.info("Provisioning: %s (AFAS ID: %s)", employee.display_name, employee.afas_employee_id)

        existing_emails = self._get_existing_emails()
        email = self.naming.generate_email(
            first_name=employee.first_name or "",
            last_name=employee.last_name or "",
            initials=employee.initials,
            existing_emails=existing_emails,
            checker=self.entra,
        )
        username = self.naming.generate_username(
            first_name=employee.first_name or "",
            last_name=employee.last_name or "",
            initials=employee.initials,
        )
        employee.generated_email = email
        employee.generated_username = username

        # Entra ID provisioning
        try:
            entra_user = self.entra.create_user(
                display_name=employee.display_name or "",
                email=email,
                mail_nickname=email.split("@")[0],
                job_title=employee.function,
                department=employee.department,
            )
            employee.entra_id_object_id = entra_user.get("id", entra_user.get("displayName", "mock"))
            self._log(
                SyncAction.PROVISION, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                f"Entra ID-account aangemaakt: {email}",
                employee=employee,
                details={"email": email, "object_id": employee.entra_id_object_id},
            )

            # Licenties toewijzen
            for sku_id in self.license_sku_ids:
                try:
                    self.entra.assign_license(employee.entra_id_object_id, sku_id)
                    self._log(
                        SyncAction.LICENSE_ASSIGN, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                        f"Licentie {sku_id} toegewezen", employee=employee,
                    )
                except Exception as e:
                    self._log(
                        SyncAction.LICENSE_ASSIGN, SyncTarget.ENTRA_ID, SyncStatus.WARNING,
                        f"Licentie toewijzen mislukt: {e}", employee=employee,
                    )

            # Groepstoewijzingen Entra ID
            entra_groups = self.mapping.get_entra_id_groups(attrs)
            for group_id in entra_groups:
                try:
                    self.entra.add_to_group(employee.entra_id_object_id, group_id)
                    self._log(
                        SyncAction.GROUP_ASSIGN, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                        f"Groep {group_id} toegewezen", employee=employee,
                    )
                except Exception as e:
                    self._log(
                        SyncAction.GROUP_ASSIGN, SyncTarget.ENTRA_ID, SyncStatus.WARNING,
                        f"Groepstoewijzing mislukt: {e}", employee=employee,
                    )

        except Exception as e:
            employee.status = EmployeeStatus.ERROR
            self._log(
                SyncAction.PROVISION, SyncTarget.ENTRA_ID, SyncStatus.ERROR,
                f"Entra ID provisioning mislukt: {e}", employee=employee,
            )
            logger.error("Entra ID provisioning mislukt voor %s: %s", employee.display_name, e)
            return

        # Active Directory provisioning (optioneel)
        if self.enable_ad and self.ad:
            try:
                ou = self.mapping.get_ou(attrs)
                ad_dn = self.ad.create_user(
                    username=username,
                    display_name=employee.display_name or "",
                    first_name=employee.first_name or "",
                    last_name=employee.last_name or "",
                    email=email,
                    ou=ou,
                    job_title=employee.function,
                    department=employee.department,
                )
                employee.ad_dn = ad_dn
                self._log(
                    SyncAction.PROVISION, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.SUCCESS,
                    f"AD-account aangemaakt: {username} in {ou}",
                    employee=employee,
                )

                # AD groepstoewijzingen
                ad_groups = self.mapping.get_ad_groups(attrs)
                for group_dn in ad_groups:
                    try:
                        self.ad.add_to_group(ad_dn, group_dn)
                        self._log(
                            SyncAction.GROUP_ASSIGN, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.SUCCESS,
                            f"AD-groep {group_dn} toegewezen", employee=employee,
                        )
                    except Exception as e:
                        self._log(
                            SyncAction.GROUP_ASSIGN, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.WARNING,
                            f"AD-groepstoewijzing mislukt: {e}", employee=employee,
                        )

            except Exception as e:
                self._log(
                    SyncAction.PROVISION, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.ERROR,
                    f"AD provisioning mislukt: {e}", employee=employee,
                )
                logger.error("AD provisioning mislukt voor %s: %s", employee.display_name, e)

        employee.status = EmployeeStatus.ACTIVE
        employee.last_synced_at = datetime.utcnow()

    def _update_provisioned_user(self, employee: Employee, attrs: dict) -> None:
        """Werk een bestaande geprovisioneerde gebruiker bij."""
        if not employee.entra_id_object_id:
            return

        try:
            self.entra.update_user(employee.entra_id_object_id, {
                "displayName": employee.display_name or "",
                "jobTitle": employee.function,
                "department": employee.department,
            })
            self._log(
                SyncAction.UPDATE, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                "Entra ID-profiel bijgewerkt", employee=employee,
            )
        except Exception as e:
            self._log(
                SyncAction.UPDATE, SyncTarget.ENTRA_ID, SyncStatus.ERROR,
                f"Entra ID update mislukt: {e}", employee=employee,
            )

        if self.enable_ad and employee.ad_dn:
            try:
                self.ad.update_user(employee.ad_dn, {
                    "displayName": employee.display_name or "",
                    "title": employee.function or "",
                    "department": employee.department or "",
                })
                self._log(
                    SyncAction.UPDATE, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.SUCCESS,
                    "AD-profiel bijgewerkt", employee=employee,
                )
            except Exception as e:
                self._log(
                    SyncAction.UPDATE, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.ERROR,
                    f"AD update mislukt: {e}", employee=employee,
                )

        employee.last_synced_at = datetime.utcnow()

    def _deprovision(self, employee: Employee, attrs: dict) -> None:
        """Deprovisioneer een uitdienstgetreden medewerker."""
        logger.info("Deprovisioning: %s (AFAS ID: %s)", employee.display_name, employee.afas_employee_id)

        # Entra ID uitschakelen
        if employee.entra_id_object_id:
            try:
                # Licenties intrekken
                self.entra.revoke_all_licenses(employee.entra_id_object_id)
                self._log(
                    SyncAction.LICENSE_REVOKE, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                    "Alle licenties ingetrokken", employee=employee,
                )

                # Uit alle groepen verwijderen
                groups = self.entra.get_user_groups(employee.entra_id_object_id)
                for group_id in groups:
                    try:
                        self.entra.remove_from_group(employee.entra_id_object_id, group_id)
                        self._log(
                            SyncAction.GROUP_REMOVE, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                            f"Verwijderd uit groep {group_id}", employee=employee,
                        )
                    except Exception:
                        pass

                # Account uitschakelen
                self.entra.disable_user(employee.entra_id_object_id)
                self._log(
                    SyncAction.DEPROVISION, SyncTarget.ENTRA_ID, SyncStatus.SUCCESS,
                    "Entra ID-account uitgeschakeld", employee=employee,
                )
            except Exception as e:
                self._log(
                    SyncAction.DEPROVISION, SyncTarget.ENTRA_ID, SyncStatus.ERROR,
                    f"Entra ID deprovisioning mislukt: {e}", employee=employee,
                )

        # Active Directory uitschakelen
        if self.enable_ad and employee.ad_dn:
            try:
                self.ad.disable_user(employee.ad_dn)
                self._log(
                    SyncAction.DEPROVISION, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.SUCCESS,
                    "AD-account uitgeschakeld", employee=employee,
                )
                # Verplaats naar Uitdienstgetreden OU
                cn = employee.display_name or employee.generated_username or "Onbekend"
                cn = cn.replace(",", "")
                new_dn = self.ad.move_to_disabled_ou(employee.ad_dn, cn)
                employee.ad_dn = new_dn
                self._log(
                    SyncAction.OU_MOVE, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.SUCCESS,
                    f"AD-account verplaatst naar uitdienstgetreden OU", employee=employee,
                )
            except Exception as e:
                self._log(
                    SyncAction.DEPROVISION, SyncTarget.ACTIVE_DIRECTORY, SyncStatus.ERROR,
                    f"AD deprovisioning mislukt: {e}", employee=employee,
                )

        employee.status = EmployeeStatus.DISABLED
        employee.last_synced_at = datetime.utcnow()
