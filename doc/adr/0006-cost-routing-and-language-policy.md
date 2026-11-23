# 0006. Routing de modelos como estrategia de costo y política de idioma

Estado: aceptado (2026-11-22)

## Contexto

`spec/05-reto.md` pide al menos una estrategia de costo medida contra un baseline con el
mismo conjunto de evaluación, distinguiendo costo estimado de facturado, y evitar cachés que
no aíslen por contexto de autorización. La caché de AI Gateway (`spec/03`) no aísla por
cliente. Además, `QA.md` pide todo en inglés, mientras el proyecto acordó documentar en
español.

## Decisión

- Estrategia del MVP: routing determinista de `spec/03` (`MODEL_SMALL` o `MODEL_LARGE`),
  ventana `HISTORY_WINDOW` y tope `MODEL_MAX_TOKENS`. El Reviewer usa siempre `MODEL_SMALL`
  y no recibe historial.
- La caché del gateway se implementa como pide `spec/03`, pero queda apagada
  (`CACHE_TTL_SECONDS=0`) y fuera de la evidencia; con `ENVIRONMENT=production` y
  `CACHE_TTL_SECONDS > 0` el producto no arranca.
- Comparación con `verification evaluate` (simulado) y `verification benchmark` (real):
  baseline `ROUTING=false` y sin ventana. Costo estimado con `spec/model_prices.json`;
  facturado "no disponible"; ahorro solo si baseline > 0.
- Idioma: identificadores, nombres de pruebas y mensajes de error de la API en inglés;
  comentarios, docstrings Sphinx, ADR, README y UI en español. Es una excepción acordada a
  `QA.md`; los demás umbrales se mantienen.

## Consecuencias

- El ahorro depende de que el modelo pequeño sostenga la calidad; si baja, la palanca no se
  usa y se informa.
- Sin caché no hay riesgo de servir respuestas de un cliente a otro, a cambio de no ahorrar
  en preguntas repetidas.
- Los revisores no reportan la mezcla de idiomas como incumplimiento.
