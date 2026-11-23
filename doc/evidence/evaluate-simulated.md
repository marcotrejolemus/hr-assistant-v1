# Costo y calidad: baseline contra optimizado (SIMULADO)

**Esta evidencia es SIMULADA.** Se obtuvo con el modelo simulado (`MODEL_PROVIDER=fake`),
sin red y sin llamar a Cloudflare. No es un consumo observado ni facturado: el costo es un
**costo estimado, no facturado**. El ahorro real se mide con
`uv run python -m verification benchmark`, que requiere las credenciales de Cloudflare de la
persona. La única corrida real existente (`benchmark.md`) es previa a F1-F3, histórica y no
concluyente; no representa el código de I7.

## Condiciones

- Fecha de la corrida: 2026-11-22 (incremento I7; la corrió el supervisor de la fábrica).
- Comando: `uv run python -m verification evaluate` (código 0).
- Conjunto fijo: `verification/eval_set.json`, 8 casos; el mismo para las dos corridas.
- Historial: el mismo en las dos corridas y en cada caso, 10 mensajes de relleno (5 pares
  `user`/`assistant`) que simulan una conversación larga (`verification/evaluate.py`).
- Datos: el mismo directorio sintético `data/employees.json`.
- Caché: apagada (`CACHE_TTL_SECONDS=0`); todas las consultas son únicas; `cached_calls = 0`.
- Calidad: fracción de casos cuya respuesta cumple `must_include` o `any_of` del caso.
- Unidad del costo: USD **estimado**, con las tarifas de `spec/model_prices.json` (USD por
  millón de tokens, fuente: página de precios de Workers AI, revisadas 2026-11-04). El modelo
  simulado recibe el nombre del modelo elegido y se cobra con el precio de ese nombre. Sus
  tokens son una aproximación por palabras, no tokens reales del proveedor.
- Costo facturado: no disponible (`cost_billed: "not_available"`).

| Configuración | Variables | Calidad | `cost_usd` (USD estimado) | `input_tokens` |
| --- | --- | --- | --- | --- |
| Baseline | `ROUTING=false`, `HISTORY_WINDOW=1000` | 100 % | 0,001541 | 4609 |
| Optimizado | por omisión: `ROUTING=true`, `HISTORY_WINDOW=6` | 100 % | 0,000267 | 4039 |

Cálculo derivado de la tabla (baseline > 0, así que se puede expresar en porcentaje):

- Reducción de costo estimado simulado: (0,001541 - 0,000267) / 0,001541 =
  0,001274 / 0,001541 = 82,7 %.
- Reducción de tokens de entrada simulados: (4609 - 4039) / 4609 = 570 / 4609 = 12,4 %.
- Calidad: sin cambio (100 % en ambas).

Los tokens de entrada son mayores que en la corrida de I6 (baseline 4150 y optimizado 3580)
porque, desde F3, el Reviewer recibe la evidencia de las herramientas de la petición
(truncada a 1500 caracteres), lo que agrega tokens a su llamada en las dos configuraciones.

No se midió por separado el aporte de cada palanca (routing y ventana); la corrida compara
solo las dos configuraciones completas.

## Lo que esta evidencia no prueba

- Que un modelo pequeño real sostenga el protocolo JSON y la calidad: eso lo mide
  `benchmark` con Cloudflare.
- Latencia real, errores reales del proveedor ni costo facturado.
- El efecto de una caché: está apagada y prohibida en producción (ADR 0006).
