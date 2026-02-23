"""Unit tests voor de MappingEngine."""
import pytest
from datetime import date
from src.engines.mapping_engine import MappingEngine


ATTRIBUTE_MAPPING = [
    {"afas_field": "Nm", "internal_field": "last_name", "transform": "none"},
    {"afas_field": "VoornaamVolledig", "internal_field": "first_name", "transform": "none"},
    {"afas_field": "Initialen", "internal_field": "initials", "transform": "none"},
    {"afas_field": "FunctionDescription", "internal_field": "function", "transform": "none"},
    {"afas_field": "DepartmentDescription", "internal_field": "department", "transform": "none"},
    {"afas_field": "StartDate", "internal_field": "start_date", "transform": "date_iso"},
    {"afas_field": "EndDate", "internal_field": "end_date", "transform": "date_iso"},
    {"afas_field": "EmId", "internal_field": "afas_employee_id", "transform": "none"},
]

GROUP_MAPPINGS = [
    {"afas_field": "department", "afas_value": "ICT", "target": "entra_id", "group_id": "ict-group-id"},
    {"afas_field": "function", "afas_value": "Manager", "target": "entra_id", "group_id": "mgr-group-id"},
    {"afas_field": "department", "afas_value": "ICT", "target": "active_directory", "group_dn": "CN=ICT,OU=Groups,DC=test,DC=local"},
    {"afas_field": "*", "afas_value": "*", "target": "entra_id", "group_id": "all-employees-group"},
]

OU_MAPPINGS = [
    {"afas_field": "department", "afas_value": "ICT", "ou": "OU=ICT,OU=Users,DC=test,DC=local"},
    {"default": "OU=Users,DC=test,DC=local"},
]


@pytest.fixture
def engine():
    return MappingEngine(
        attribute_mapping=ATTRIBUTE_MAPPING,
        group_mappings=GROUP_MAPPINGS,
        ou_mappings=OU_MAPPINGS,
    )


class TestMapEmployee:
    def test_basic_mapping(self, engine):
        record = {
            "EmId": "123",
            "Nm": "de Vries",
            "VoornaamVolledig": "Jan",
            "Initialen": "J.",
            "FunctionDescription": "Developer",
            "DepartmentDescription": "ICT",
            "StartDate": "2023-01-15",
            "EndDate": None,
        }
        result = engine.map_employee(record)
        assert result["afas_employee_id"] == "123"
        assert result["last_name"] == "de Vries"
        assert result["first_name"] == "Jan"
        assert result["department"] == "ICT"
        assert isinstance(result["start_date"], date)
        assert result["start_date"] == date(2023, 1, 15)

    def test_missing_fields_become_none(self, engine):
        record = {"EmId": "456"}
        result = engine.map_employee(record)
        assert result["afas_employee_id"] == "456"
        assert result.get("last_name") is None

    def test_date_transform(self, engine):
        record = {"StartDate": "2024-06-01", "EndDate": "2024-12-31"}
        result = engine.map_employee(record)
        assert result.get("start_date") == date(2024, 6, 1)
        assert result.get("end_date") == date(2024, 12, 31)


class TestGroupMappings:
    def test_ict_gets_entra_group(self, engine):
        attrs = {"department": "ICT", "function": "Developer"}
        groups = engine.get_entra_id_groups(attrs)
        assert "ict-group-id" in groups
        assert "all-employees-group" in groups

    def test_manager_gets_manager_group(self, engine):
        attrs = {"department": "HR", "function": "Manager"}
        groups = engine.get_entra_id_groups(attrs)
        assert "mgr-group-id" in groups

    def test_ict_gets_ad_group(self, engine):
        attrs = {"department": "ICT"}
        groups = engine.get_ad_groups(attrs)
        assert "CN=ICT,OU=Groups,DC=test,DC=local" in groups

    def test_non_matching_gets_no_specific_group(self, engine):
        attrs = {"department": "Finance", "function": "Controller"}
        entra_groups = engine.get_entra_id_groups(attrs)
        assert "ict-group-id" not in entra_groups
        assert "all-employees-group" in entra_groups  # Wildcard geldt altijd


class TestOuMappings:
    def test_ict_gets_ict_ou(self, engine):
        attrs = {"department": "ICT"}
        ou = engine.get_ou(attrs)
        assert ou == "OU=ICT,OU=Users,DC=test,DC=local"

    def test_other_gets_default_ou(self, engine):
        attrs = {"department": "Finance"}
        ou = engine.get_ou(attrs)
        assert ou == "OU=Users,DC=test,DC=local"
