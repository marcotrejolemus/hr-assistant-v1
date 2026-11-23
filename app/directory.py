"""Directorio de empleados de solo lectura cargado al arrancar."""

import json
from pathlib import Path
from typing import Dict, List, Union


def _normalize(text: str) -> str:
    """Normaliza un texto para compararlo sin mayúsculas ni espacios extra.

    :param text: Texto original.
    :type text: str
    :return: Texto normalizado.
    :rtype: str
    """
    return " ".join(text.split()).casefold()


class EmployeeDirectory:
    """Directorio de empleados leído una sola vez desde un archivo JSON.

    :param path: Ruta del archivo de empleados.
    :type path: str or pathlib.Path
    :raises FileNotFoundError: Si el archivo no existe.
    :raises ValueError: Si el archivo no es JSON válido o no es una lista de
        empleados.
    """

    def __init__(self, path: Union[str, Path]):
        file_path = Path(path)
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid employees file {file_path}: {error}") from error
        if not isinstance(raw, list) or not all(
            isinstance(item, dict) and "id" in item for item in raw
        ):
            raise ValueError(f"Employees file {file_path} must be a list of objects")
        self._employees = tuple(dict(item) for item in raw)

    def get_employee(self, employee_id: str) -> Dict[str, str]:
        """Busca un empleado por su id.

        :param employee_id: Id del empleado, por ejemplo ``EMP-0004``.
        :type employee_id: str
        :return: Copia de los datos del empleado o un objeto ``error`` si no existe.
        :rtype: dict
        """
        wanted = employee_id.strip().upper()
        for employee in self._employees:
            if str(employee["id"]).upper() == wanted:
                return dict(employee)
        return {"error": f"No existe un empleado con id {employee_id}"}

    def search_by_department(self, department: str) -> List[Dict[str, str]]:
        """Lista los empleados de un departamento.

        La comparación ignora mayúsculas y espacios sobrantes.

        :param department: Nombre del departamento.
        :type department: str
        :return: Copias de los empleados del departamento (vacía si no hay).
        :rtype: list[dict]
        """
        wanted = _normalize(department)
        return [
            dict(employee)
            for employee in self._employees
            if _normalize(str(employee.get("department", ""))) == wanted
        ]

    def departments(self) -> List[str]:
        """Devuelve los departamentos que existen en los datos, sin repetir.

        :return: Nombres de departamento en orden de aparición.
        :rtype: list[str]
        """
        names: List[str] = []
        for employee in self._employees:
            name = employee.get("department")
            if name and name not in names:
                names.append(name)
        return names
