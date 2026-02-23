"""Unit tests voor de NamingEngine."""
import pytest
from src.engines.naming_engine import NamingEngine


@pytest.fixture
def engine():
    return NamingEngine(
        domain="bedrijf.nl",
        pattern="{initials}.{lastname}@{domain}",
        fallback_patterns=[
            "{initials}.{lastname}{n}@{domain}",
            "{firstname}.{lastname}@{domain}",
        ],
        username_pattern="{initials}.{lastname}",
    )


class TestNormalizeName:
    def test_basic(self, engine):
        assert engine.normalize_name("Vries") == "vries"

    def test_spaces_removed(self, engine):
        assert engine.normalize_name("van den Berg") == "vandenberg"

    def test_diacritics(self, engine):
        assert engine.normalize_name("Müller") == "muller"
        assert engine.normalize_name("Désiré") == "desire"

    def test_hyphens_removed(self, engine):
        assert engine.normalize_name("Jansen-Bakker") == "jansenbakker"

    def test_apostrophe_removed(self, engine):
        assert engine.normalize_name("O'Brien") == "obrien"


class TestExtractInitials:
    def test_single_name(self, engine):
        assert engine.extract_initials("Jan") == "j"

    def test_double_first_name(self, engine):
        assert engine.extract_initials("Jan Peter") == "jp"

    def test_triple_name(self, engine):
        assert engine.extract_initials("Maria Anna Loes") == "mal"


class TestGenerateEmail:
    def test_basic_generation(self, engine):
        email = engine.generate_email("Jan", "de Vries")
        assert email == "j.devries@bedrijf.nl"

    def test_duplicate_gets_number(self, engine):
        existing = {"j.devries@bedrijf.nl"}
        email = engine.generate_email("Jan", "de Vries", existing_emails=existing)
        assert email == "j.devries2@bedrijf.nl"

    def test_multiple_duplicates(self, engine):
        existing = {"j.devries@bedrijf.nl", "j.devries2@bedrijf.nl", "j.devries3@bedrijf.nl"}
        email = engine.generate_email("Jan", "de Vries", existing_emails=existing)
        assert email == "j.devries4@bedrijf.nl"

    def test_with_initials(self, engine):
        email = engine.generate_email("Jan Peter", "Bakker", initials="J.P.")
        assert email == "jp.bakker@bedrijf.nl"

    def test_checker_protocol(self, engine):
        class MockChecker:
            def user_exists(self, email: str) -> bool:
                return email == "j.devries@bedrijf.nl"

        email = engine.generate_email("Jan", "de Vries", checker=MockChecker())
        assert email == "j.devries2@bedrijf.nl"

    def test_diacritics_in_name(self, engine):
        email = engine.generate_email("Jörg", "Müller")
        assert email == "j.muller@bedrijf.nl"


class TestGenerateUsername:
    def test_basic(self, engine):
        username = engine.generate_username("Jan", "Bakker")
        assert username == "j.bakker"

    def test_max_length(self, engine):
        username = engine.generate_username("Jan", "VanDenBergstraatenwaterweg")
        assert len(username) <= 20

    def test_duplicate_gets_number(self, engine):
        existing = {"j.bakker"}
        username = engine.generate_username("Jan", "Bakker", existing_usernames=existing)
        assert username == "j.bakker2"
