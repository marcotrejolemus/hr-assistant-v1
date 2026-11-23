"""Tabla de precios por modelo y costo estimado de cada llamada (``spec/03``).

Los precios vienen de ``data/model_prices.json`` en USD por millón de tokens. El
costo es una estimación: el costo facturado no se conoce desde el producto.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Union

from app.config import Settings

TOKENS_PER_UNIT = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    """Precio de un modelo en USD por millón de tokens.

    :param input: Precio de los tokens de entrada.
    :type input: float
    :param output: Precio de los tokens de salida.
    :type output: float
    """

    input: float
    output: float


@dataclass(frozen=True)
class PriceTable:
    """Precios de todos los modelos conocidos.

    :param models: Precio por nombre de modelo.
    :type models: Mapping[str, ModelPrice]
    """

    models: Mapping[str, ModelPrice]

    def has_price(self, model: str) -> bool:
        """Indica si el modelo tiene precio.

        :param model: Nombre del modelo.
        :type model: str
        :return: ``True`` si aparece en la tabla.
        :rtype: bool
        """
        return model in self.models

    def cost(self, model: str, *, input_tokens: int, output_tokens: int) -> float:
        """Calcula el costo estimado de una llamada en USD.

        :param model: Nombre del modelo que atendió la llamada.
        :type model: str
        :param input_tokens: Tokens de entrada.
        :type input_tokens: int
        :param output_tokens: Tokens de salida.
        :type output_tokens: int
        :return: ``(entrada * precio_entrada + salida * precio_salida) / 1e6``.
        :rtype: float
        :raises ValueError: Si el modelo no tiene precio.
        """
        price = self.models.get(model)
        if price is None:
            raise ValueError("model without price")
        total = input_tokens * price.input + output_tokens * price.output
        return total / TOKENS_PER_UNIT


def load_prices(path: Union[str, Path]) -> PriceTable:
    """Lee la tabla de precios de un archivo JSON con la forma de ``spec/03``.

    :param path: Ruta del archivo de precios.
    :type path: str or pathlib.Path
    :return: La tabla de precios.
    :rtype: PriceTable
    :raises ValueError: Si el archivo no existe o no tiene la forma esperada; el
        mensaje nombra ``PRICES_PATH``.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        models = {
            name: ModelPrice(
                input=float(price["input"]), output=float(price["output"])
            )
            for name, price in data["models"].items()
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("PRICES_PATH must point to a valid prices file") from error
    return PriceTable(models=models)


def require_configured_prices(prices: PriceTable, settings: Settings) -> None:
    """Exige precio para ``MODEL_SMALL`` y ``MODEL_LARGE`` antes de arrancar.

    :param prices: Tabla de precios cargada.
    :type prices: PriceTable
    :param settings: Configuración validada.
    :type settings: Settings
    :raises ValueError: Si un modelo configurado no tiene precio; el mensaje
        nombra la variable.
    """
    configured = (
        ("MODEL_SMALL", settings.model_small),
        ("MODEL_LARGE", settings.model_large),
    )
    for variable, model in configured:
        if not prices.has_price(model):
            raise ValueError(f"{variable} has no price in PRICES_PATH")
