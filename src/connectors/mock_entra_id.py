"""Mock Entra ID-connector voor demo- en testdoeleinden.

Simuleert Microsoft Entra ID-operaties in geheugen/database.
"""
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory opslag voor de mock (wordt gereset bij herstart)
_MOCK_USERS: dict[str, dict] = {}          # object_id -> user dict
_MOCK_GROUPS: dict[str, set] = {}          # group_id -> set of object_ids
_EMAIL_INDEX: dict[str, str] = {}          # email -> object_id


class MockEntraIdConnector:
    """Mock Entra ID-connector voor demo-modus."""

    def __init__(self, domain: str = "demo.nl", **kwargs):
        self.domain = domain

    def user_exists(self, email: str) -> bool:
        return email.lower() in {e.lower() for e in _EMAIL_INDEX}

    def get_user(self, object_id: str) -> Optional[dict]:
        return _MOCK_USERS.get(object_id)

    def create_user(
        self,
        display_name: str,
        email: str,
        mail_nickname: str,
        temp_password: str = "Welkom@2024!",
        job_title: Optional[str] = None,
        department: Optional[str] = None,
    ) -> dict:
        object_id = str(uuid.uuid4())
        user = {
            "id": object_id,
            "displayName": display_name,
            "mail": email,
            "userPrincipalName": email,
            "mailNickname": mail_nickname,
            "accountEnabled": True,
            "jobTitle": job_title,
            "department": department,
        }
        _MOCK_USERS[object_id] = user
        _EMAIL_INDEX[email.lower()] = object_id
        logger.info("Mock Entra ID: gebruiker aangemaakt %s (%s)", display_name, email)
        return user

    def update_user(self, object_id: str, attributes: dict) -> None:
        if object_id in _MOCK_USERS:
            _MOCK_USERS[object_id].update(attributes)
        logger.info("Mock Entra ID: gebruiker bijgewerkt %s", object_id)

    def disable_user(self, object_id: str) -> None:
        if object_id in _MOCK_USERS:
            _MOCK_USERS[object_id]["accountEnabled"] = False
        logger.info("Mock Entra ID: gebruiker uitgeschakeld %s", object_id)

    def assign_license(self, object_id: str, sku_id: str) -> None:
        logger.info("Mock Entra ID: licentie %s toegewezen aan %s", sku_id, object_id)

    def revoke_all_licenses(self, object_id: str) -> None:
        logger.info("Mock Entra ID: alle licenties ingetrokken voor %s", object_id)

    def add_to_group(self, object_id: str, group_id: str) -> None:
        if group_id not in _MOCK_GROUPS:
            _MOCK_GROUPS[group_id] = set()
        _MOCK_GROUPS[group_id].add(object_id)
        logger.info("Mock Entra ID: %s toegevoegd aan groep %s", object_id, group_id)

    def remove_from_group(self, object_id: str, group_id: str) -> None:
        if group_id in _MOCK_GROUPS:
            _MOCK_GROUPS[group_id].discard(object_id)
        logger.info("Mock Entra ID: %s verwijderd uit groep %s", object_id, group_id)

    def get_user_groups(self, object_id: str) -> list[str]:
        return [gid for gid, members in _MOCK_GROUPS.items() if object_id in members]

    def test_connection(self) -> bool:
        logger.info("Mock Entra ID verbindingstest geslaagd")
        return True
