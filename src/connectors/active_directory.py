"""Active Directory connector via LDAP (ldap3).

Beheert gebruikersaccounts in een on-premises Active Directory.
"""
import logging
import ssl
from typing import Optional
import ldap3
from ldap3 import Server, Connection, ALL, Tls, SUBTREE, MODIFY_REPLACE, MODIFY_ADD, MODIFY_DELETE
from ldap3.extend.microsoft import ad_add_members_to_groups, ad_remove_members_from_groups

logger = logging.getLogger(__name__)

# userAccountControl waarden
UAC_NORMAL_ACCOUNT = 512        # Ingeschakeld
UAC_ACCOUNT_DISABLE = 514       # Uitgeschakeld


class ActiveDirectoryConnector:
    """Connector voor on-premises Active Directory via LDAP."""

    def __init__(
        self,
        server: str,
        base_dn: str,
        bind_user: str,
        bind_password: str,
        port: int = 636,
        use_ssl: bool = True,
        disabled_ou: Optional[str] = None,
    ):
        self.server_addr = server
        self.base_dn = base_dn
        self.bind_user = bind_user
        self.bind_password = bind_password
        self.port = port
        self.use_ssl = use_ssl
        self.disabled_ou = disabled_ou or f"OU=Uitdienstgetreden,{base_dn}"
        self._conn: Optional[Connection] = None

    def _get_connection(self) -> Connection:
        """Maak een LDAP-verbinding aan (of hergebruik bestaande)."""
        if self._conn and self._conn.bound:
            return self._conn

        tls_config = None
        if self.use_ssl:
            tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLS_CLIENT)

        server = Server(
            self.server_addr,
            port=self.port,
            use_ssl=self.use_ssl,
            tls=tls_config,
            get_info=ALL,
        )
        conn = Connection(
            server,
            user=self.bind_user,
            password=self.bind_password,
            auto_bind=True,
        )
        self._conn = conn
        return conn

    def user_exists(self, username: str) -> bool:
        """Controleer of een gebruiker al bestaat in AD (op sAMAccountName)."""
        conn = self._get_connection()
        conn.search(
            search_base=self.base_dn,
            search_filter=f"(&(objectClass=user)(sAMAccountName={username}))",
            search_scope=SUBTREE,
            attributes=["sAMAccountName"],
        )
        return len(conn.entries) > 0

    def get_user_dn(self, username: str) -> Optional[str]:
        """Zoek de DN op van een gebruiker op basis van sAMAccountName."""
        conn = self._get_connection()
        conn.search(
            search_base=self.base_dn,
            search_filter=f"(&(objectClass=user)(sAMAccountName={username}))",
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
        )
        if conn.entries:
            return str(conn.entries[0].distinguishedName)
        return None

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
        """Maak een nieuwe gebruiker aan in Active Directory. Geeft de DN terug."""
        conn = self._get_connection()

        # Bouw de CN op (Common Name in de OU)
        cn = display_name.replace(",", "")  # Komma's zijn niet toegestaan in CN
        user_dn = f"CN={cn},{ou}"

        attributes = {
            "objectClass": ["top", "person", "organizationalPerson", "user"],
            "sAMAccountName": username,
            "userPrincipalName": email,
            "displayName": display_name,
            "givenName": first_name,
            "sn": last_name,
            "mail": email,
            "userAccountControl": str(UAC_NORMAL_ACCOUNT),
        }
        if job_title:
            attributes["title"] = job_title
        if department:
            attributes["department"] = department

        conn.add(user_dn, attributes=attributes)
        if not conn.result["result"] == 0:
            raise RuntimeError(f"AD gebruiker aanmaken mislukt: {conn.result}")

        # Stel wachtwoord in (vereist TLS)
        try:
            unicode_pass = f'"{temp_password}"'.encode("utf-16-le")
            conn.modify(user_dn, {"unicodePwd": [(MODIFY_REPLACE, [unicode_pass])]})
        except Exception as e:
            logger.warning("Kon AD-wachtwoord niet instellen voor %s: %s", username, e)

        logger.info("AD gebruiker aangemaakt: %s in %s", username, ou)
        return user_dn

    def update_user(self, user_dn: str, attributes: dict) -> None:
        """Werk attributen van een bestaande AD-gebruiker bij."""
        conn = self._get_connection()
        changes = {key: [(MODIFY_REPLACE, [value])] for key, value in attributes.items()}
        conn.modify(user_dn, changes)
        if conn.result["result"] != 0:
            raise RuntimeError(f"AD gebruiker bijwerken mislukt: {conn.result}")
        logger.info("AD gebruiker bijgewerkt: %s", user_dn)

    def disable_user(self, user_dn: str) -> None:
        """Schakel een AD-gebruikersaccount uit."""
        conn = self._get_connection()
        conn.modify(user_dn, {"userAccountControl": [(MODIFY_REPLACE, [str(UAC_ACCOUNT_DISABLE)])]})
        logger.info("AD gebruiker uitgeschakeld: %s", user_dn)

    def move_to_disabled_ou(self, user_dn: str, cn: str) -> str:
        """Verplaats een account naar de 'Uitdienstgetreden' OU."""
        conn = self._get_connection()
        conn.modify_dn(user_dn, f"CN={cn}", new_superior=self.disabled_ou)
        new_dn = f"CN={cn},{self.disabled_ou}"
        logger.info("AD gebruiker verplaatst naar %s", self.disabled_ou)
        return new_dn

    def add_to_group(self, user_dn: str, group_dn: str) -> None:
        """Voeg een gebruiker toe aan een AD-groep."""
        conn = self._get_connection()
        try:
            ad_add_members_to_groups(conn, user_dn, group_dn)
            logger.info("Gebruiker %s toegevoegd aan groep %s", user_dn, group_dn)
        except Exception as e:
            logger.warning("Kon gebruiker niet toevoegen aan groep %s: %s", group_dn, e)

    def remove_from_group(self, user_dn: str, group_dn: str) -> None:
        """Verwijder een gebruiker uit een AD-groep."""
        conn = self._get_connection()
        try:
            ad_remove_members_from_groups(conn, user_dn, group_dn)
            logger.info("Gebruiker %s verwijderd uit groep %s", user_dn, group_dn)
        except Exception as e:
            logger.warning("Kon gebruiker niet verwijderen uit groep %s: %s", group_dn, e)

    def test_connection(self) -> bool:
        """Test de verbinding met Active Directory."""
        try:
            conn = self._get_connection()
            return conn.bound
        except Exception as e:
            logger.error("AD verbindingstest mislukt: %s", e)
            return False

    def close(self) -> None:
        """Sluit de LDAP-verbinding."""
        if self._conn and self._conn.bound:
            self._conn.unbind()
            self._conn = None
