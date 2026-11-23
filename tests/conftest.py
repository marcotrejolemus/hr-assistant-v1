"""Fixtures compartidas: datos del producto y la app con dependencias inyectadas.

Las pruebas nunca leen el entorno del proceso: arman la configuración con
``load_settings`` a partir de un diccionario explícito.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PRODUCT_DIR = Path(__file__).resolve().parent.parent
if str(PRODUCT_DIR) not in sys.path:
    sys.path.insert(0, str(PRODUCT_DIR))

# Estas importaciones van después de insertar ``product/`` en ``sys.path``: sin
# eso, un ``pytest`` lanzado sin ``python -m`` no encuentra el paquete ``app``.
# pylint: disable=wrong-import-position
from doubles import PRICES_PATH, TEST_API_KEYS, TEST_KEY, FixedClock
from app.config import load_settings
from app.directory import EmployeeDirectory
from app.llm import build_model
from app.main import create_app

# pylint: enable=wrong-import-position

DATA_PATH = PRODUCT_DIR / "data" / "employees.json"


@pytest.fixture
def directory():
    """El directorio de empleados con los datos del producto."""
    return EmployeeDirectory(DATA_PATH)


@pytest.fixture
def make_settings():
    """Fábrica de configuración a partir de variables explícitas.

    Desde I4 la configuración trae por omisión un cliente de prueba ficticio
    (``TEST_API_KEYS``) y un límite alto de peticiones, para que las pruebas de
    I1 a I3 sigan comprobando lo mismo con la clave obligatoria.

    :return: Función que recibe variables de entorno y devuelve ``Settings``.
    """

    def _make(**environ):
        defaults = {
            "EMPLOYEES_PATH": str(DATA_PATH),
            "PRICES_PATH": str(PRICES_PATH),
            "API_KEYS": TEST_API_KEYS,
            "RATE_LIMIT_PER_MINUTE": "1000",
        }
        return load_settings({**defaults, **environ})

    return _make


@pytest.fixture
def make_app(directory, make_settings):
    """Fábrica de la app con configuración, modelo y directorio inyectados.

    Sin modelo explícito se usa ``build_model``, que respeta los ``FAKE_*``.

    :param directory: Directorio de empleados de la fixture ``directory``.
    :param make_settings: Fábrica de configuración.
    :return: Función que recibe un modelo opcional y variables de entorno.
    """

    def _make(model=None, **environ):
        settings = make_settings(**environ)
        model = model or build_model(settings, directory)
        return create_app(settings=settings, model=model, directory=directory)

    return _make


def _key_headers(api_key):
    """Encabezados por omisión del cliente: ``X-API-Key`` si hay clave.

    :param api_key: Clave que manda el cliente, o ``None`` para no mandar ninguna.
    :type api_key: str or None
    :return: Encabezados del ``TestClient``.
    :rtype: dict
    """
    return {} if api_key is None else {"X-API-Key": api_key}


@pytest.fixture
def make_client(make_app):
    """Fábrica de ``TestClient`` sobre la app con dependencias inyectadas.

    Por omisión el cliente manda la clave de prueba ficticia en ``X-API-Key``;
    con ``api_key=None`` no manda ninguna.

    :param make_app: Fábrica de la app.
    :return: Función que recibe un modelo opcional, la clave y variables de
        entorno.
    """

    def _make(model=None, api_key=TEST_KEY, **environ):
        return TestClient(make_app(model, **environ), headers=_key_headers(api_key))

    return _make


@pytest.fixture
def log_lines():
    """Líneas JSON que el producto escribe en el ``log_sink`` inyectado."""
    return []


@pytest.fixture
def make_observed_client(directory, make_settings, log_lines):
    """Fábrica de ``TestClient`` con reloj fijo y log capturado en ``log_lines``.

    No relanza las excepciones del servidor, para poder ver la respuesta 500.
    Por omisión manda la clave de prueba ficticia; con ``api_key=None``, ninguna.

    :param directory: Directorio de empleados.
    :param make_settings: Fábrica de configuración.
    :param log_lines: Lista donde se acumulan las líneas del log.
    :return: Función que recibe un modelo opcional, una fábrica opcional de
        clientes de trazas, la clave y variables de entorno.
    """

    def _make(model=None, trace_client_factory=None, api_key=TEST_KEY, **environ):
        settings = make_settings(**environ)
        model = model or build_model(settings, directory)
        app = create_app(
            settings=settings,
            model=model,
            directory=directory,
            clock=FixedClock(),
            log_sink=log_lines.append,
            trace_client_factory=trace_client_factory,
        )
        return TestClient(
            app, raise_server_exceptions=False, headers=_key_headers(api_key)
        )

    return _make
