"""Mock Active Directory-connector voor demo- en testdoeleinden."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MOCK_AD_USERS: dict[str, dict] = {}    # dn -> user dict
_MOCK_AD_GROUPS: dict[str, set] = {}   # group_dn -> set of user_dns
_USERNAME_INDEX: dict[str, str] = {}    # username -> dn


class MockActiveDirectoryConnector:
    """Mock Active Directory-connector voor demo-modus."""

    def __init__(self, base_dn: str = "DC=demo,DC=local", disabled_ou: Optional[str] = None, **kwargs):
        self.base_dn = base_dn
        self.disabled_ou = disabled_ou or f"OU=Uitdienstgetreden,{base_dn}"

    def user_exists(self, username: str) -> bool:
        return username.lower() in {u.lower() for u in _USERNAME_INDEX}

    def get_user_dn(self, username: str) -> Optional[str]:
        return _USERNAME_INDEX.get(username.lower())

    def create_user(
        self,
        username: str,
        display_name: str,
        first_name: str,
        last_name: str,
        email: str,
        ou: str,
        job_title: Optional[str] = None,
        department: Optional[str] = None,
        temp_password: str = "Welkom@2024!",
    ) -> str:
        cn = display_name.replace(",", "")
        user_dn = f"CN={cn},{ou}"
        _MOCK_AD_USERS[user_dn] = {
            "dn": user_dn,
            "sAMAccountName": username,
            "displayName": display_name,
            "givenName": first_name,
            "sn": last_name,
            "mail": email,
            "title": job_title,
            "department": department,
            "userAccountControl": 512,  # Ingeschakeld
        }
        _USERNAME_INDEX[username.lower()] = user_dn
        logger.info("Mock AD: gebruiker aangemaakt %s (%s)", username, user_dn)
        return user_dn

    def update_user(self, user_dn: str, attributes: dict) -> None:
        if user_dn in _MOCK_AD_USERS:
            _MOCK_AD_USERS[user_dn].update(attributes)
        logger.info("Mock AD: gebruiker bijgewerkt %s", user_dn)

    def disable_user(self, user_dn: str) -> None:
        if user_dn in _MOCK_AD_USERS:
            _MOCK_AD_USERS[user_dn]["userAccountControl"] = 514  # Uitgeschakeld
        logger.info("Mock AD: gebruiker uitgeschakeld %s", user_dn)

    def move_to_disabled_ou(self, user_dn: str, cn: str) -> str:
        new_dn = f"CN={cn},{self.disabled_ou}"
        if user_dn in _MOCK_AD_USERS:
            user = _MOCK_AD_USERS.pop(user_dn)
            user["dn"] = new_dn
            _MOCK_AD_USERS[new_dn] = user
            # Bijwerken username index
            username = user.get("sAMAccountName", "")
            if username:
                _USERNAME_INDEX[username.lower()] = new_dn
        logger.info("Mock AD: gebruiker verplaatst naar %s", self.disabled_ou)
        return new_dn

    def add_to_group(self, user_dn: str, group_dn: str) -> None:
        if group_dn not in _MOCK_AD_GROUPS:
            _MOCK_AD_GROUPS[group_dn] = set()
        _MOCK_AD_GROUPS[group_dn].add(user_dn)
        logger.info("Mock AD: %s toegevoegd aan groep %s", user_dn, group_dn)

    def remove_from_group(self, user_dn: str, group_dn: str) -> None:
        if group_dn in _MOCK_AD_GROUPS:
            _MOCK_AD_GROUPS[group_dn].discard(user_dn)
        logger.info("Mock AD: %s verwijderd uit groep %s", user_dn, group_dn)

    def test_connection(self) -> bool:
        logger.info("Mock AD verbindingstest geslaagd")
        return True

    def close(self) -> None:
        pass
