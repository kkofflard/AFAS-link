"""Microsoft Entra ID (Azure AD) connector via Microsoft Graph API.

Gebruikt MSAL voor authenticatie en de Graph API voor gebruikersbeheer.
"""
import logging
from typing import Optional
import msal
import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class EntraIdConnector:
    """Connector voor Microsoft Entra ID via de Microsoft Graph API."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, domain: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.domain = domain
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

    def _get_token(self) -> str:
        """Haal een geldig Bearer-token op via MSAL."""
        result = self._msal_app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Onbekende fout"))
            raise RuntimeError(f"Kon geen Entra ID-token ophalen: {error}")
        return result["access_token"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        with httpx.Client(timeout=30) as client:
            response = client.get(f"{GRAPH_BASE}{path}", headers=self._headers(), params=params)
            response.raise_for_status()
            return response.json()

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{GRAPH_BASE}{path}", headers=self._headers(), json=body)
            response.raise_for_status()
            return response.json() if response.content else {}

    def _patch(self, path: str, body: dict) -> None:
        with httpx.Client(timeout=30) as client:
            response = client.patch(f"{GRAPH_BASE}{path}", headers=self._headers(), json=body)
            response.raise_for_status()

    def _delete(self, path: str) -> None:
        with httpx.Client(timeout=30) as client:
            response = client.delete(f"{GRAPH_BASE}{path}", headers=self._headers())
            response.raise_for_status()

    def user_exists(self, email: str) -> bool:
        """Controleer of een gebruiker met dit e-mailadres al bestaat in Entra ID."""
        try:
            result = self._get("/users", params={"$filter": f"mail eq '{email}' or userPrincipalName eq '{email}'"})
            return len(result.get("value", [])) > 0
        except httpx.HTTPStatusError:
            return False

    def get_user(self, object_id: str) -> Optional[dict]:
        """Haal gebruikersgegevens op via het Entra ID object-ID."""
        try:
            return self._get(f"/users/{object_id}")
        except httpx.HTTPStatusError:
            return None

    def create_user(
        self,
        display_name: str,
        email: str,
        mail_nickname: str,
        temp_password: str = "Welkom@2024!",
        job_title: Optional[str] = None,
        department: Optional[str] = None,
    ) -> dict:
        """Maak een nieuwe gebruiker aan in Entra ID."""
        body: dict = {
            "accountEnabled": True,
            "displayName": display_name,
            "mailNickname": mail_nickname,
            "userPrincipalName": email,
            "mail": email,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": temp_password,
            },
        }
        if job_title:
            body["jobTitle"] = job_title
        if department:
            body["department"] = department

        result = self._post("/users", body)
        logger.info("Entra ID gebruiker aangemaakt: %s (ID: %s)", email, result.get("id"))
        return result

    def update_user(self, object_id: str, attributes: dict) -> None:
        """Werk gebruikersattributen bij in Entra ID."""
        self._patch(f"/users/{object_id}", attributes)
        logger.info("Entra ID gebruiker bijgewerkt: %s", object_id)

    def disable_user(self, object_id: str) -> None:
        """Schakel een gebruiker uit in Entra ID."""
        self._patch(f"/users/{object_id}", {"accountEnabled": False})
        logger.info("Entra ID gebruiker uitgeschakeld: %s", object_id)

    def assign_license(self, object_id: str, sku_id: str) -> None:
        """Wijs een licentie toe aan een gebruiker."""
        body = {
            "addLicenses": [{"skuId": sku_id, "disabledPlans": []}],
            "removeLicenses": [],
        }
        self._post(f"/users/{object_id}/assignLicense", body)
        logger.info("Licentie %s toegewezen aan %s", sku_id, object_id)

    def revoke_all_licenses(self, object_id: str) -> None:
        """Trek alle licenties in van een gebruiker."""
        user = self.get_user(object_id)
        if not user:
            return
        assigned = [lic["skuId"] for lic in user.get("assignedLicenses", [])]
        if assigned:
            body = {"addLicenses": [], "removeLicenses": assigned}
            self._post(f"/users/{object_id}/assignLicense", body)
            logger.info("Alle licenties ingetrokken voor %s", object_id)

    def add_to_group(self, object_id: str, group_id: str) -> None:
        """Voeg een gebruiker toe aan een beveiligingsgroep."""
        body = {"@odata.id": f"{GRAPH_BASE}/users/{object_id}"}
        try:
            self._post(f"/groups/{group_id}/members/$ref", body)
            logger.info("Gebruiker %s toegevoegd aan groep %s", object_id, group_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "already exist" in e.response.text.lower():
                logger.debug("Gebruiker %s is al lid van groep %s", object_id, group_id)
            else:
                raise

    def remove_from_group(self, object_id: str, group_id: str) -> None:
        """Verwijder een gebruiker uit een beveiligingsgroep."""
        try:
            self._delete(f"/groups/{group_id}/members/{object_id}/$ref")
            logger.info("Gebruiker %s verwijderd uit groep %s", object_id, group_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug("Gebruiker %s is geen lid van groep %s", object_id, group_id)
            else:
                raise

    def get_user_groups(self, object_id: str) -> list[str]:
        """Haal de groeps-IDs op van een gebruiker."""
        result = self._get(f"/users/{object_id}/memberOf")
        return [group["id"] for group in result.get("value", []) if group.get("@odata.type") == "#microsoft.graph.group"]

    def test_connection(self) -> bool:
        """Test de verbinding met Microsoft Entra ID."""
        try:
            self._get("/organization")
            return True
        except Exception as e:
            logger.error("Entra ID verbindingstest mislukt: %s", e)
            return False
