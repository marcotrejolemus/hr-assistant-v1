# 0004. Supervisor determinista con dos agentes LLM: Directory Specialist y Reviewer

Estado: aceptado (2026-11-22)

## Contexto

`spec/05-reto.md` pide una orquestación acotada con supervisor, especialista de directorio y
revisión de entradas y salidas, sin presentar funciones auxiliares como agentes LLM. También
pide concurrencia sin bloquear el event loop, límites de pasos, timeouts y respuestas
predecibles si el proveedor cae. Los contratos fijan `steps == 2` para `EMP-0004`, `502
model unavailable` y los estados de `review`.

## Decisión

- Supervisor, Input Guard, Router de costo y Output Guard son código determinista. Solo hay
  dos agentes LLM: el Directory Specialist (el `Agent` actual, con `get_employee` y
  `search_by_department`) y el Reviewer (sin herramientas, una llamada con `MODEL_SMALL`,
  salida `{"verdict": "approve"|"reject", "issues": [...]}`).
- El Reviewer aconseja; el Output Guard decide siempre. `reject` da una respuesta segura
  fija; Reviewer caído, sin presupuesto o con JSON inválido da `review.status =
  "unavailable"` y la respuesta sale solo si pasa el Output Guard.
- La interfaz de ADR 0002 conserva su nombre y pasa a async:
  `complete(messages, *, model, max_tokens)`. Cada llamada usa `asyncio.wait_for` con el
  menor entre `MODEL_TIMEOUT_SECONDS` y el tiempo restante de `REQUEST_TIMEOUT_SECONDS`.
- Límites validados al arrancar: `AGENT_MAX_STEPS`, `REVIEWER_MAX_CALLS`,
  `MAX_MODEL_CALLS_PER_REQUEST` (>= la suma de los dos anteriores), `MODEL_MAX_TOKENS` y
  `REQUEST_INPUT_TOKEN_BUDGET`.
- `steps` cuenta solo las llamadas del Specialist; `model_calls` cuenta todas.

## Consecuencias

- Las responsabilidades se ven por separado en logs y trazas (`supervisor`,
  `input_guard`, `directory_specialist`, `reviewer_agent`, `output_guard`).
- Cada respuesta cuesta una llamada más (Reviewer); se mide en `model_calls` y `cost_usd`.
- Las pruebas existentes se adaptan a la interfaz async sin cambiar el contrato de sesión 1.
- El modelo simulado debe distinguir el rol Reviewer y aceptar `FAKE_MODEL_FAIL`,
  `FAKE_REVIEWER_VERDICT` y `FAKE_REVIEWER_FAIL`, solo con `MODEL_PROVIDER=fake`.

## Revisión 2026-11-23 (I7, calidad con modelo real)

La decisión original y su estado no cambian; esta revisión ajusta cómo se interpreta la
salida de los agentes y qué ve el Reviewer.

- Motivo: el benchmark real con Cloudflare mostró que el Specialist con el modelo pequeño
  envolvía el JSON en bloques de código o texto y agotaba sus pasos, y que el Reviewer
  rechazaba respuestas correctas porque no veía los datos de las herramientas.
- F1: `extract_json_object` (en `app/llm.py`) acepta exactamente un objeto JSON de primer
  nivel, dentro o fuera de un bloque de código y con texto alrededor; rechaza varios
  objetos, arreglos, varios bloques, JSON inválido o ausencia de objeto. Después se aplica
  la misma validación estricta de esquema (Specialist: `answer` o `tool` + `args` con el
  único parámetro permitido; Reviewer: exactamente `verdict` e `issues`), sin alias ni
  campos extra; `tool_denied` se sigue auditando. Caso límite documentado: un objeto
  exterior sin cerrar que contiene uno interior completo acepta el interior y luego decide
  el esquema.
- F2: cuando la respuesta del Specialist no se puede interpretar o ejecutar, el mensaje de
  corrección recuerda el formato exacto; no hay llamadas extra.
- F3: el Reviewer recibe, además de la pregunta y el borrador, la evidencia de esta petición
  (resultados de herramientas serializados y truncados a 1500 caracteres, o «No se consultó
  ninguna herramienta»). Aprueba si el borrador es consistente con la evidencia y rechaza
  solo por datos inventados, contradicciones, secretos o instrucciones. Sigue sin historial,
  herramientas ni secretos, con `MODEL_SMALL`, una llamada y veredicto estricto; el Output
  Guard decide siempre. Esto alinea la implementación con el Plan Maestro v2 (sección 2).
- Consecuencia: el Reviewer consume más tokens de entrada por la evidencia; el efecto en
  calidad y costo reales se mide con `verification benchmark` (pendiente de una nueva
  corrida autorizada por la persona).
