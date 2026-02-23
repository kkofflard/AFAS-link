"""Naamgevingsengine voor het genereren van e-mailadressen en gebruikersnamen.

Ondersteunt configureerbare patronen en automatische duplicaatdetectie.
"""
import logging
import re
import unicodedata
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

# Veelvoorkomende Nederlandse tussenvoegels
TUSSENVOEGSELS = {
    "de", "den", "der", "van", "van de", "van den", "van der",
    "van het", "'t", "te", "ter", "ten", "op", "op de", "in",
    "in de", "in het", "aan", "aan de", "voor",
}


class EmailExistenceChecker(Protocol):
    """Protocol voor het controleren van bestaande e-mailadressen."""
    def user_exists(self, email: str) -> bool: ...


class NamingEngine:
    """Genereert unieke e-mailadressen en gebruikersnamen op basis van configureerbare patronen."""

    def __init__(
        self,
        domain: str,
        pattern: str = "{initials}.{lastname}@{domain}",
        fallback_patterns: Optional[list[str]] = None,
        username_pattern: str = "{initials}.{lastname}",
        strip_tussenvoegsel: bool = False,
    ):
        self.domain = domain
        self.pattern = pattern
        self.fallback_patterns = fallback_patterns or [
            "{initials}.{lastname}{n}@{domain}",
            "{firstname}.{lastname}@{domain}",
            "{firstname}.{lastname}{n}@{domain}",
        ]
        self.username_pattern = username_pattern
        self.strip_tussenvoegsel = strip_tussenvoegsel

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normaliseer een naam voor gebruik in e-mailadres:
        - Zet om naar ASCII (bijv. é → e)
        - Verwijder spaties, koppeltekens, apostrofs
        - Zet om naar kleine letters
        """
        # Vervang diakritische tekens (é → e, ü → u, etc.)
        normalized = unicodedata.normalize("NFD", name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        # Verwijder spaties, koppeltekens en apostrofs
        clean = re.sub(r"[\s\-'']", "", ascii_name)
        return clean.lower()

    @staticmethod
    def extract_initials(first_name: str) -> str:
        """Extraheer initialen vanuit een voornaam (eerste letter van elk naamdeel)."""
        parts = first_name.strip().split()
        initials = "".join(p[0].lower() for p in parts if p)
        return initials

    def _strip_tussenvoegsel(self, last_name: str) -> str:
        """Verwijder tussenvoegsel uit achternaam als dit geconfigureerd is."""
        if not self.strip_tussenvoegsel:
            return last_name
        parts = last_name.strip().split()
        result_parts = []
        skip_next = False
        for i, part in enumerate(parts):
            lower_part = part.lower().rstrip("'")
            # Controleer eenvoudige en samengestelde tussenvoegels
            if lower_part in TUSSENVOEGSELS:
                # Controleer ook "van den", "van der" etc. (2-delig)
                if i + 1 < len(parts):
                    combo = f"{lower_part} {parts[i+1].lower()}"
                    if combo in TUSSENVOEGSELS:
                        skip_next = True
                continue
            if skip_next:
                skip_next = False
                continue
            result_parts.append(part)
        return " ".join(result_parts) if result_parts else last_name

    def _render_pattern(
        self,
        pattern: str,
        initials: str,
        firstname: str,
        lastname: str,
        n: Optional[int] = None,
    ) -> str:
        """Render een patroon met de opgegeven waarden."""
        result = pattern.format(
            initials=initials,
            firstname=firstname,
            lastname=lastname,
            domain=self.domain,
            n=n or "",
        )
        return result.lower()

    def generate_email(
        self,
        first_name: str,
        last_name: str,
        initials: Optional[str] = None,
        existing_emails: Optional[set[str]] = None,
        checker: Optional[EmailExistenceChecker] = None,
    ) -> str:
        """Genereer een uniek e-mailadres.

        Args:
            first_name: Voornaam van de medewerker
            last_name: Achternaam van de medewerker
            initials: Initialen (optioneel, anders automatisch berekend)
            existing_emails: Set van al bekende e-mailadressen in de lokale DB
            checker: Connector om te controleren of een e-mail al bestaat in Entra ID/AD

        Returns:
            Uniek gegenereerd e-mailadres
        """
        # Bereid basiswaarden voor
        if not initials:
            initials = self.extract_initials(first_name)
        else:
            initials = initials.replace(".", "").lower()

        clean_last = self.normalize_name(self._strip_tussenvoegsel(last_name))
        clean_first = self.normalize_name(first_name)

        existing = existing_emails or set()

        def _is_taken(email: str) -> bool:
            if email in existing:
                return True
            if checker and checker.user_exists(email):
                return True
            return False

        # Probeer primair patroon
        candidate = self._render_pattern(self.pattern, initials, clean_first, clean_last)
        if not _is_taken(candidate):
            return candidate

        # Probeer fallback patronen
        for fallback in self.fallback_patterns:
            if "{n}" in fallback:
                # Probeer nummers 2-99
                for n in range(2, 100):
                    candidate = self._render_pattern(fallback, initials, clean_first, clean_last, n=n)
                    if not _is_taken(candidate):
                        return candidate
            else:
                candidate = self._render_pattern(fallback, initials, clean_first, clean_last)
                if not _is_taken(candidate):
                    return candidate

        # Uiterst geval: UUID-gebaseerd adres
        import uuid
        fallback_email = f"{clean_first}.{clean_last}.{uuid.uuid4().hex[:6]}@{self.domain}"
        logger.warning(
            "Alle naampatronen uitgeput voor %s %s, gebruik UUID-fallback: %s",
            first_name, last_name, fallback_email
        )
        return fallback_email

    def generate_username(
        self,
        first_name: str,
        last_name: str,
        initials: Optional[str] = None,
        existing_usernames: Optional[set[str]] = None,
    ) -> str:
        """Genereer een unieke gebruikersnaam (voor sAMAccountName in AD)."""
        if not initials:
            initials = self.extract_initials(first_name)
        else:
            initials = initials.replace(".", "").lower()

        clean_last = self.normalize_name(self._strip_tussenvoegsel(last_name))
        clean_first = self.normalize_name(first_name)

        existing = existing_usernames or set()

        pattern = self.username_pattern
        candidate = pattern.format(initials=initials, firstname=clean_first, lastname=clean_last)
        candidate = candidate[:20]  # AD sAMAccountName max 20 tekens

        if candidate not in existing:
            return candidate

        for n in range(2, 100):
            numbered = f"{candidate[:18]}{n}"
            if numbered not in existing:
                return numbered

        import uuid
        return f"{clean_first[:3]}{uuid.uuid4().hex[:8]}"
