"""Pruebas del directorio de empleados de solo lectura."""

import pytest

from app.directory import EmployeeDirectory


def test_unknown_employee_is_reported(directory):
    result = directory.get_employee("EMP-9999")

    assert "EMP-9999" in str(result)
    assert "name" not in result


def test_department_search_ignores_case_and_spaces(directory):
    people = directory.search_by_department("  tecnología ")

    names = {person["name"] for person in people}
    assert names == {"Ana López", "Marta Ruiz", "Jorge Díaz"}
    assert directory.search_by_department("Marketing") == []


def test_missing_data_file_fails_at_startup(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError)):
        EmployeeDirectory(tmp_path / "missing.json")
