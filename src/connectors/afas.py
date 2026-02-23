"""AFAS Profit REST API connector.

Verbindt met de AFAS REST API via token-authenticatie en haalt medewerkergegevens op.
Documentatie: https://docs.afas.help/profit/en/
"""
import base64
import logging
from datetime import datetime
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

AFAS_BASE_URL = "https://{env_nr}.rest.afas.online/profitrestservices"


class AfasConnector:
    """Connector voor de AFAS Profit REST API."""

    def __init__(self, environment_nr: str, token: str, connector_id: str = "HrPersonContact"):
        self.environment_nr = environment_nr
        self.connector_id = connector_id
        self._encoded_token = self._encode_token(token)
        self.base_url = AFAS_BASE_URL.format(env_nr=environment_nr)

    @staticmethod
    def _encode_token(raw_token: str) -> str:
        """Codeer het AFAS-token naar het vereiste Base64-formaat."""
        token_xml = f"<token><version>1</version><data>{raw_token}</data></token>"
        return base64.b64encode(token_xml.encode()).decode()

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"AfasToken {self._encoded_token}",
            "Content-Type": "application/json",
        }

    def _build_url(self, connector_id: Optional[str] = None) -> str:
        cid = connector_id or self.connector_id
        return f"{self.base_url}/connectors/{cid}"

    def get_employees(
        self,
        modified_since: Optional[datetime] = None,
        skip: int = 0,
        take: int = 100,
    ) -> list[dict]:
        """Haal medewerkers op uit AFAS, optioneel gefilterd op mutatiedatum."""
        url = self._build_url()
        params: dict = {"skip": skip, "take": take}

        if modified_since:
            # AFAS filteropties: filterfieldids, filtervalues, operatortypes
            # Operator 4 = groter dan of gelijk aan
            params["filterfieldids"] = "Mutatiedatum"
            params["filtervalues"] = modified_since.strftime("%Y-%m-%dT%H:%M:%S")
            params["operatortypes"] = "4"

        all_employees: list[dict] = []
        while True:
            params["skip"] = skip
            try:
                with httpx.Client(timeout=30) as client:
                    response = client.get(url, headers=self._get_headers(), params=params)
                    response.raise_for_status()
                    data = response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "AFAS API HTTP-fout %s voor omgeving %s: %s",
                    e.response.status_code, self.environment_nr, e.response.text
                )
                raise
            except httpx.RequestError as e:
                logger.error("AFAS API verbindingsfout voor omgeving %s: %s", self.environment_nr, e)
                raise

            rows = data.get("rows", [])
            all_employees.extend(rows)

            # Stop als we minder records kregen dan gevraagd (laatste pagina)
            if len(rows) < take:
                break
            skip += take

        logger.info(
            "AFAS omgeving %s: %d medewerkers opgehaald%s",
            self.environment_nr,
            len(all_employees),
            f" (gewijzigd na {modified_since.isoformat()})" if modified_since else ""
        )
        return all_employees

    def test_connection(self) -> bool:
        """Test de verbinding met AFAS."""
        try:
            url = self._build_url()
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    url, headers=self._get_headers(), params={"skip": 0, "take": 1}
                )
                response.raise_for_status()
            return True
        except Exception as e:
            logger.error("AFAS verbindingstest mislukt voor omgeving %s: %s", self.environment_nr, e)
            return False
