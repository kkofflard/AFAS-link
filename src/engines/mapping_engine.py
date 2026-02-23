"""Mapping-engine voor AFAS-attribuuttransformatie en groepstoewijzing.

Transformeert AFAS-veldnamen en -waarden naar interne modelvelden
op basis van YAML-configuratie, zonder aangepaste code.
"""
import logging
from datetime import datetime, date
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MappingEngine:
    """Verwerkt attribuutmapping en groepstoewijzingsregels vanuit YAML-configuratie."""

    def __init__(
        self,
        attribute_mapping: list[dict],
        group_mappings: list[dict],
        ou_mappings: list[dict],
    ):
        self.attribute_mapping = attribute_mapping
        self.group_mappings = group_mappings
        self.ou_mappings = ou_mappings

    @staticmethod
    def _transform(value: Any, transform: str) -> Any:
        """Pas een transformatie toe op een waarde."""
        if value is None:
            return None
        transform = (transform or "none").lower()

        if transform == "none":
            return value
        elif transform == "lowercase":
            return str(value).lower()
        elif transform == "uppercase":
            return str(value).upper()
        elif transform == "strip":
            return str(value).strip()
        elif transform == "date_iso":
            # Zet diverse datumformaten om naar date
            if isinstance(value, (date, datetime)):
                return value.date() if isinstance(value, datetime) else value
            if isinstance(value, str):
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        return datetime.strptime(value[:len(fmt)], fmt).date()
                    except (ValueError, IndexError):
                        continue
            return None
        else:
            logger.warning("Onbekende transformatie: %s", transform)
            return value

    def map_employee(self, afas_record: dict) -> dict:
        """Zet een AFAS-medewerkerrecord om naar een intern attribuutdict."""
        result = {}
        for mapping in self.attribute_mapping:
            afas_field = mapping.get("afas_field")
            internal_field = mapping.get("internal_field")
            transform = mapping.get("transform", "none")

            if not afas_field or not internal_field:
                continue

            raw_value = afas_record.get(afas_field)
            result[internal_field] = self._transform(raw_value, transform)

        return result

    def get_entra_id_groups(self, employee_attrs: dict) -> list[str]:
        """Bepaal welke Entra ID-groepen een medewerker moet krijgen op basis van HR-attributen."""
        group_ids = []
        for rule in self.group_mappings:
            if rule.get("target") != "entra_id":
                continue
            if self._rule_matches(rule, employee_attrs):
                group_id = rule.get("group_id")
                if group_id:
                    group_ids.append(group_id)
        return group_ids

    def get_ad_groups(self, employee_attrs: dict) -> list[str]:
        """Bepaal welke AD-groepen een medewerker moet krijgen op basis van HR-attributen."""
        group_dns = []
        for rule in self.group_mappings:
            if rule.get("target") != "active_directory":
                continue
            if self._rule_matches(rule, employee_attrs):
                group_dn = rule.get("group_dn")
                if group_dn:
                    group_dns.append(group_dn)
        return group_dns

    def get_ou(self, employee_attrs: dict) -> str:
        """Bepaal de juiste OU voor een medewerker in Active Directory."""
        for rule in self.ou_mappings:
            if "default" in rule:
                continue  # Standaard als laatste
            if self._rule_matches(rule, employee_attrs):
                return rule["ou"]

        # Standaard OU
        for rule in self.ou_mappings:
            if "default" in rule:
                return rule["default"]

        return "OU=Medewerkers,DC=bedrijf,DC=local"

    @staticmethod
    def _rule_matches(rule: dict, employee_attrs: dict) -> bool:
        """Controleer of een mappingregel van toepassing is op een medewerker."""
        afas_field = rule.get("afas_field")
        afas_value = rule.get("afas_value")

        # Wildcard: geldt voor iedereen
        if afas_field == "*" and afas_value == "*":
            return True

        employee_value = employee_attrs.get(afas_field)
        if employee_value is None:
            return False

        return str(employee_value).lower() == str(afas_value).lower()

    def build_display_name(self, first_name: str, last_name: str) -> str:
        """Stel een weergavenaam samen."""
        parts = [p.strip() for p in [first_name, last_name] if p and p.strip()]
        return " ".join(parts)
