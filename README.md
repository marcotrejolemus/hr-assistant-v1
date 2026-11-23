## Video demostrativo

### HR Assistant v1 — Sistema Multiagente con IA | ITESM Módulo 4

Demostración académica del funcionamiento local de HR Assistant v1, desarrollado mediante una fábrica de agentes con Claude Code, Python y FastAPI.

El video presenta la interacción con el asistente, su arquitectura multiagente y las evidencias técnicas del proyecto.

**[▶ Ver video demostrativo en YouTube](https://www.youtube.com/watch?v=KyJm3TwO5EI)**

> Nota: La demostración local utiliza un modelo simulado. Las validaciones de producción se documentan por separado.
>
### Aplicación desplegada en Render

**URL pública:** https://hr-assistant-v1.onrender.com/

[Acceder a HR Assistant v1](https://hr-assistant-v1.onrender.com/)

La aplicación está desplegada en Render mediante Docker, con integración continua en GitHub Actions y autenticación por API Key.

**Estado de validación:** el servicio web está disponible y la autenticación funciona. La validación funcional completa con el modelo real continúa en revisión debido a respuestas bloqueadas por los controles de seguridad.

**Nota:** para realizar consultas se requiere una API Key autorizada. Las credenciales no se publican en este repositorio.
# HR Assistant

Asistente de Recursos Humanos que responde preguntas en español sobre empleados sintéticos.
Una API FastAPI sin estado sirve una página web y el endpoint `POST /ask`. En cada pregunta,
un supervisor determinista coordina guardas deterministas y dos agentes LLM: el Directory
Specialist (con dos herramientas de solo lectura sobre `data/employees.json`) y el Reviewer.

Estado: el proyecto NO está listo para entregarse. Los requisitos de I7 que dependen de la
persona (benchmark real, LangSmith real, publicación, Render, CI en GitHub, PR y video) siguen
en NOT RUN. Ver "Pruebas y resultados" y "Limitaciones".

Datos: todos los empleados son sintéticos. No hay datos reales.

## Arquitectura

El detalle, con diagramas Mermaid, está en [doc/architecture.md](doc/architecture.md) (runtime,
lo que atiende peticiones) y [doc/factory.md](doc/factory.md) (fábrica, los agentes de Claude
Code que construyeron el producto). Son cosas distintas: los agentes del runtime son solo dos.

Diagrama de texto de `POST /ask`:

```text
Navegador (static/index.html)  o  cliente HTTP
        |  POST /ask + X-API-Key
        v
Middleware: X-Request-ID (se respeta o se genera)
        v
Auth X-API-Key (401) -> Rate limit por cliente (429) -> Esquema Pydantic (422)
        v
Supervisor (determinista): presupuestos de llamadas, tokens y tiempo
        v
Input Guard (determinista: pii.py + guards.py)
   |-- inyección o exfiltración ------------> 400 "request blocked by policy"
   |-- PII redactada ([REDACTED:<tipo>]) antes de proveedor, logs y trazas
        v
Router de costo (determinista): MODEL_SMALL o MODEL_LARGE + HISTORY_WINDOW
        v
Directory Specialist (agente LLM, agent.py)
   |-- prompt de sistema fijo; bucle hasta AGENT_MAX_STEPS
   |-- get_employee / search_by_department -> directory.py (solo lectura)
   |-- herramienta desconocida o args inválidos -> auditoría tool_denied
   |-- proveedor caído o tiempo agotado --> 502 "model unavailable"
        v  borrador + evidencia de las herramientas
Reviewer (agente LLM, reviewer.py): MODEL_SMALL, sin herramientas, sin historial
   |-- recibe pregunta redactada, borrador (máx. 2000 caracteres) y la evidencia
   |   de las herramientas de esta petición, truncada a 1500 caracteres (F3)
   |-- veredicto: approve, reject o unavailable (solo aconseja)
        v
Output Guard (determinista, decide siempre)
   |-- reject, secreto, marcador de prompt o exceso de largo -> 200 con respuesta segura fija
   |-- PII nueva en la salida: se redacta
        v
200: answer, steps, tools_used, tokens, model_calls, review, redactions,
     request_id, model, route, cached_calls, cost_usd
```

Componentes de `product/app/`:

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | API FastAPI, rutas, middleware de `request_id`, autenticación y límite por cliente |
| `config.py` | Única lectura del entorno; valida y falla con mensajes que nombran la variable, nunca el valor |
| `security.py` | Claves por cliente, comparación en tiempo constante, `RateLimiter`, reglas de producción |
| `supervisor.py` | Orquesta guardas, router y los dos agentes; aplica los presupuestos |
| `guards.py`, `pii.py` | Input Guard, Output Guard y detección de PII |
| `router.py` | Elige el modelo y aplica la ventana de historial |
| `agent.py` | Directory Specialist |
| `reviewer.py` | Reviewer |
| `directory.py` | Herramientas de solo lectura sobre los empleados sintéticos |
| `llm.py` | Interfaz async del modelo, modelo simulado y cliente de Cloudflare AI Gateway |
| `costs.py`, `metrics.py` | Precios, costo estimado y métricas de proceso |
| `observability.py`, `clock.py` | Logs JSON, auditoría, trazas de LangSmith a prueba de fallas y reloj inyectado |

## Agentes y decisiones

Agentes del runtime (LLM): Directory Specialist y Reviewer. El supervisor, el Input Guard, el
Router de costo y el Output Guard son código determinista, no agentes LLM. El Reviewer aconseja;
el Output Guard decide siempre.

Agentes de la fábrica (Claude Code, en `.claude/agents/`): architect, qa-unit, developer,
observability, costs, security, deploy, qa-e2e, qa-style y triage. Cada uno escribe solo en sus
carpetas, lo hace cumplir `hooks/permissions.py`, y los pasos de `verification/` deciden por
código de salida. Ver [doc/factory.md](doc/factory.md).

Decisiones de arquitectura (ADR):

- [0001 API sin estado](doc/adr/0001-stateless-api.md)
- [0002 Interfaz del modelo](doc/adr/0002-model-interface.md)
- [0003 Inyección de dependencias](doc/adr/0003-dependency-injection.md)
- [0004 Supervisor determinista con Directory Specialist y Reviewer](doc/adr/0004-multiagent-supervisor-reviewer.md),
  incluye la revisión de I7 (F1 a F3: extracción estricta de JSON, mensaje de corrección y
  evidencia para el Reviewer)
- [0005 Guardas deterministas de PII e inyección, con falla segura](doc/adr/0005-pii-guards-fail-safe.md)
- [0006 Routing de modelos como estrategia de costo y política de idioma](doc/adr/0006-cost-routing-and-language-policy.md)

Política de idioma (ADR 0006): identificadores, nombres de pruebas y mensajes de error de la API
en inglés; comentarios, docstrings, ADR, README y UI en español. Es una excepción acordada a
`QA.md`.

## Setup local

Requisitos: Python 3.12. Las variables se leen solo del entorno del proceso; el producto no lee
archivos `.env`. `.env.example` es una plantilla con los nombres y los secretos vacíos.

Desde la carpeta `product/`:

```text
pip install -r requirements.txt
```

Con el modelo simulado (sin red, sin Cloudflare), en bash:

```text
export MODEL_PROVIDER=fake
export API_KEYS="demo:<tu-clave>"
uvicorn app.main:app --port 8000
```

En PowerShell:

```text
$env:MODEL_PROVIDER = "fake"
$env:API_KEYS = "demo:<tu-clave>"
uvicorn app.main:app --port 8000
```

`API_KEYS` tiene la forma `cliente:clave,cliente2:clave2`. Debe definirse antes de arrancar: el
módulo `app.main` crea la aplicación al importarse. Sin `API_KEYS`, `POST /ask` y `GET /metrics`
responden siempre 401 (no existe ningún bypass). Cada cliente manda su clave en la cabecera
`X-API-Key`:

```text
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <tu-clave>" \
  -d '{"question": "¿Quién es EMP-0004?"}'
```

Abre `http://127.0.0.1:8000/` para la página web (la clave se escribe en un campo de tipo
contraseña y vive en `sessionStorage`) y `http://127.0.0.1:8000/docs` para Swagger.

Con el modelo real (Cloudflare AI Gateway): `MODEL_PROVIDER=gateway` exige `CF_ACCOUNT_ID`,
`CF_GATEWAY_ID` y `CF_API_TOKEN`; sin alguna de ellas el producto no arranca.

## Docker

Desde `product/`. El `-e API_KEYS` sin valor toma la variable de tu terminal, así que la clave
no queda escrita en el comando ni en el historial:

```text
docker build -t hr-assistant-v1 .
docker run -d --name hr-assistant-v1 -p 127.0.0.1:8000:8000 \
  -e PORT=8000 -e ENVIRONMENT=development -e MODEL_PROVIDER=fake \
  -e API_KEYS hr-assistant-v1
```

La imagen parte de `python:3.12-slim`, copia `requirements.txt`, `app/` y `data/`, y corre
como usuario no root (uid 10001). Escucha en `${PORT:-8000}`. No lleva secretos: llegan como
variables de entorno. Ver las limitaciones sobre las dependencias de prueba que hoy trae.

## Comandos de verificación

Se corren desde la raíz del repositorio de la fábrica (no desde `product/`) con
`uv run python -m verification <paso>`. Código 0: pasa. Código 3: NOT RUN (nunca cuenta como
PASS). Otro código: falla.

| Paso | Qué hace | Qué requiere |
| --- | --- | --- |
| `unit` | Pruebas de `product/tests` (unitarias y Gherkin) con cobertura mínima de 80 % | Dependencias de `requirements.txt` instaladas |
| `contract [--all]` | Contratos de `verification/contract/` contra el producto corriendo con el modelo simulado; sin `--all`, los contratos de incrementos posteriores al alcanzado salen como PENDING (no es PASS) | Ninguna credencial; el paso arranca el producto por su cuenta |
| `qa` | Parte mecánica de `QA.md` (pylint, 88 columnas) | pylint en el entorno de la fábrica |
| `e2e` | Pruebas de Playwright de `product/e2e/` contra el producto vivo | Playwright y Chromium instalados (CI los instala aparte de `requirements.txt`) |
| `evaluate` | Costo y calidad, baseline contra palancas, con el modelo simulado; pasa solo si la calidad no baja y el costo sí | Ninguna credencial; resultado SIMULADO |
| `security` | Contratos de seguridad completos y escaneo de secretos de `product/` | Ninguna credencial |
| `load [<url>] [--evidencia]` | 10 solicitudes concurrentes a `/ask`; local por omisión, remoto con URL | Remoto: variable `SMOKE_API_KEY` en tu terminal (sin ella, NOT RUN) |
| `docker` | Build, contenedor local, `/health`, `/docs`, `/ask` sin y con clave, usuario no root | Docker instalado (sin él, NOT RUN) |
| `production <url>` | Prueba de humo contra la URL publicada | Variable `SMOKE_API_KEY` |
| `benchmark [--evidencia]` | Baseline contra optimizado con Cloudflare real | `CF_ACCOUNT_ID` y `CF_API_TOKEN` en la terminal de la persona (sin ellas, NOT RUN); lo corre la persona |

Las claves nunca se escriben en el comando: se leen de variables de entorno.

## API

| Método y ruta | Clave | Descripción |
| --- | --- | --- |
| `GET /` | No | Página web |
| `GET /health` | No | `{"status": "ok", "pid": <n>}` |
| `GET /docs`, `GET /openapi.json` | No | Swagger y esquema OpenAPI (declara el esquema `X-API-Key`) |
| `GET /metrics` | Sí | Métricas del proceso: peticiones, latencias, tokens, costo estimado por modelo, rutas; `cost_billed` siempre `not_available` |
| `POST /ask` | Sí | Responde una pregunta |

Cuerpo de `POST /ask`: `question` (texto no vacío, máximo `MAX_QUESTION_CHARS`) e `history`
opcional (lista de `{"role": "user"|"assistant", "content": ...}`, máximo
`MAX_HISTORY_MESSAGES` mensajes, cada uno con el mismo largo máximo). Toda respuesta lleva la
cabecera `X-Request-ID` (el del cliente si es seguro, o un UUID nuevo).

Respuesta 200: `answer`, `steps` (llamadas del Specialist), `tools_used`, `input_tokens`,
`output_tokens`, `model_calls` (todas las llamadas), `review` (`status`: `approved`,
`rejected` o `unavailable`, e `issue_count`; el texto de los problemas nunca se devuelve),
`redactions` (tipos de PII redactados), `request_id`, `model`, `route`, `cached_calls` y
`cost_usd` (estimado, no facturado).

Códigos de error:

| Código | Cuándo | Cuerpo |
| --- | --- | --- |
| 400 | Inyección o exfiltración detectada | `{"detail": "request blocked by policy", "request_id": ...}` |
| 401 | Sin clave o clave inválida en `/ask` o `/metrics` | `{"detail": "invalid or missing API key"}` |
| 422 | Esquema, largo o número de mensajes inválidos; no se llama al modelo | Validación estándar de FastAPI |
| 429 | Más de `RATE_LIMIT_PER_MINUTE` peticiones por cliente y minuto | `{"detail": "rate limit exceeded"}` con cabecera `Retry-After` |
| 500 | Error inesperado | `{"detail": "internal error", "request_id": ...}`; el log guarda solo el tipo del error |
| 502 | Proveedor caído o tiempo agotado en el Specialist | `{"detail": "model unavailable", "request_id": ...}` |

No existe el código 504: el tiempo agotado termina en 502 (Specialist) o en
`review.status = "unavailable"` (Reviewer). Si el Reviewer rechaza, la respuesta es 200 con una
respuesta segura fija. Si el Specialist agota presupuesto o pasos, es 200 con un mensaje fijo
de tope.

## Variables de entorno

Solo nombres. Los valores van en el entorno de quien corre el producto o en Render. Los
valores por omisión están en `app/config.py`.

| Grupo | Variables |
| --- | --- |
| Proveedor y entorno | `MODEL_PROVIDER` (`fake` o `gateway`), `ENVIRONMENT` (`development` o `production`), `EMPLOYEES_PATH`, `PORT` (solo la imagen Docker) |
| Acceso (secreta la primera) | `API_KEYS`, `RATE_LIMIT_PER_MINUTE` |
| Cloudflare (obligatorias con `gateway`; `CF_API_TOKEN` es secreta) | `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_API_TOKEN` |
| Modelos y palancas de costo | `MODEL_SMALL`, `MODEL_LARGE`, `ROUTING`, `ROUTER_MAX_CHARS`, `HISTORY_WINDOW`, `MODEL_MAX_TOKENS`, `MODEL_TEMPERATURE`, `CACHE_TTL_SECONDS`, `PRICES_PATH` |
| Límites del supervisor | `AGENT_MAX_STEPS`, `REVIEWER_MAX_CALLS`, `MAX_MODEL_CALLS_PER_REQUEST`, `REQUEST_INPUT_TOKEN_BUDGET`, `MODEL_TIMEOUT_SECONDS`, `REQUEST_TIMEOUT_SECONDS`, `MAX_QUESTION_CHARS`, `MAX_HISTORY_MESSAGES`, `MAX_ANSWER_CHARS` |
| Observabilidad (`LANGSMITH_API_KEY` es secreta) | `SERVICE_NAME`, `SLO_P95_MS`, `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `HIDE_INPUTS`, `HIDE_OUTPUTS` |
| Solo pruebas con `MODEL_PROVIDER=fake` | `FAKE_MODEL_FAIL`, `FAKE_REVIEWER_VERDICT`, `FAKE_REVIEWER_FAIL` |
| Solo para las verificaciones de la fábrica | `SMOKE_API_KEY` (`load <url>` y `production <url>`), `E2E_API_KEY` (pruebas de Playwright) |

Reglas de validación: un valor inválido impide arrancar y el error nombra la variable, nunca el
valor. `MAX_MODEL_CALLS_PER_REQUEST` debe ser al menos `AGENT_MAX_STEPS + REVIEWER_MAX_CALLS`.
Los `FAKE_*` solo se aceptan con `MODEL_PROVIDER=fake`. `MODEL_SMALL` y `MODEL_LARGE` deben
tener precio en la tabla de precios. Las variables desconocidas se ignoran.

## Seguridad

La lista completa, con dónde está cada regla en el código y cómo se comprueba, está en
[doc/compliance-checklist.md](doc/compliance-checklist.md). Resumen:

- Autenticación por cliente con `X-API-Key` en `/ask` y `/metrics`; comparación en tiempo
  constante; sin `API_KEYS` todo es 401. Las claves no salen en `repr`, errores ni logs.
- Límite de peticiones por cliente y minuto (429 con `Retry-After`).
- Con `ENVIRONMENT=production` el producto se niega a arrancar si: el modelo es `fake`,
  `API_KEYS` está vacía o tiene una clave de menos de 16 caracteres, hay trazas encendidas con
  `HIDE_INPUTS` o `HIDE_OUTPUTS` en `false`, hay algún `FAKE_*` definido, o
  `CACHE_TTL_SECONDS` es mayor que 0.
- PII (email, teléfono, CURP, RFC, tarjeta con Luhn) redactada antes del proveedor, de los logs
  y de las trazas; el Output Guard redacta PII nueva y reemplaza salidas con secretos, prompt de
  sistema o exceso de largo por una respuesta segura fija (ADR 0005).
- Inyección y exfiltración (español e inglés) responden 400.
- Herramientas de solo lectura y con argumentos validados; una herramienta rechazada no se
  ejecuta y deja auditoría `tool_denied` sin argumentos.
- Auditoría en el log JSON (`auth_denied`, `rate_limited`, `policy_block`, `pii_redacted`,
  `review_verdict`, `output_blocked`, `tool_call`, `tool_denied`) con `request_id` y `client`,
  nunca con claves, PII ni texto de preguntas o respuestas.
- Las trazas de LangSmith están apagadas por omisión; `HIDE_INPUTS` y `HIDE_OUTPUTS` valen
  `true` por omisión. Un fallo de telemetría no cambia la respuesta (evento `telemetry_error`).
- La página pinta con `textContent`, nunca con `innerHTML`.
- Secretos solo por variables de entorno; `.env.example` trae únicamente nombres;
  `verification security` escanea `product/` en busca de secretos.

## Costos y palancas

El costo de cada petición se estima con la tabla de precios (`data/model_prices.json`, USD por
millón de tokens) y se devuelve en `cost_usd`. Es estimado: el costo facturado figura como no
disponible (`cost_billed: "not_available"` en `/metrics`) y debe consultarse en el dashboard del
proveedor.

Palancas (ADR 0006):

- Routing determinista: preguntas largas (más de `ROUTER_MAX_CHARS`) o con palabras de
  complejidad van a `MODEL_LARGE`; las simples, a `MODEL_SMALL` (`ROUTING`).
- Ventana de historial: el Specialist recibe solo los últimos `HISTORY_WINDOW` mensajes.
- Tope de tokens de salida (`MODEL_MAX_TOKENS`), de llamadas por petición y de tokens de entrada
  estimados por petición (`REQUEST_INPUT_TOKEN_BUDGET`).
- El Reviewer usa siempre `MODEL_SMALL` y no recibe historial.
- Caché del gateway: implementada pero apagada (`CACHE_TTL_SECONDS=0`) y prohibida en
  producción, porque no aísla por cliente.

Evidencia simulada: `verification evaluate` (modelo simulado, costo estimado, no facturado) dio
en la corrida de I7 una calidad de 100 % en ambas configuraciones, 0,001541 USD estimados y 4609
tokens de entrada para el baseline (`ROUTING=false`, `HISTORY_WINDOW=1000`), y 0,000267 USD
estimados y 4039 tokens de entrada con las palancas. Es una simulación: no prueba que un modelo
pequeño real sostenga la calidad. La evidencia con modelos reales sigue en NOT RUN (ver
"Limitaciones").

## Trade-offs

- Un Reviewer LLM agrega una llamada por petición (más costo y latencia) a cambio de una segunda
  opinión; como solo aconseja y el Output Guard decide, su falla no bloquea la respuesta.
- La evidencia que recibe el Reviewer (F3) lo hace más preciso, pero sube sus tokens de entrada
  (en `evaluate`, de 4150 en I6 a 4609 en el baseline de I7).
- El routing y la ventana ahorran costo, pero un modelo pequeño puede perder calidad; si la
  calidad baja, la palanca no se usa y se informa (ADR 0006).
- Sin caché no hay riesgo de servir la respuesta de un cliente a otro, a cambio de no ahorrar en
  preguntas repetidas.
- Los filtros deterministas son reproducibles y se prueban sin red, pero dan falsos positivos
  (por ejemplo, preguntar por una "API key") y pueden dejar pasar PII en formatos no previstos.
- Sin estado entre peticiones (ADR 0001): el historial lo envía el cliente en cada pregunta.
  Métricas y límite de peticiones son estado de instancia, por proceso.
- Una sola instancia gratuita en Render: sencilla y barata, pero el servicio puede dormirse y
  tardar hasta un minuto en responder.

## Render y CI

Render (Blueprint [render.yaml](render.yaml)): un servicio web `hr-assistant-v1`, `runtime:
docker`, plan `free`, `healthCheckPath: /health` y `autoDeployTrigger: checksPass` (publica solo
si el CI pasa). Fija `ENVIRONMENT=production`, `MODEL_PROVIDER=gateway`, `CF_GATEWAY_ID`,
`HIDE_INPUTS`, `HIDE_OUTPUTS`, `CACHE_TTL_SECONDS=0` y `LANGSMITH_PROJECT`. Los secretos
`API_KEYS`, `CF_ACCOUNT_ID` y `CF_API_TOKEN` llevan `sync: false`: su valor se escribe solo en
Render. `LANGSMITH_API_KEY` y `LANGSMITH_TRACING=true` se agregan en Render > Environment cuando
se quieran trazas.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)): se dispara en `push` y
`pull_request`, con permiso de solo lectura y cuatro etapas encadenadas:

1. `style`: pylint (88 columnas, nota mínima 10).
2. `unit`: pytest sobre `tests` con cobertura mínima de 80 %, con el modelo simulado.
3. `e2e`: Playwright en Chromium contra el producto local con el modelo simulado.
4. `docker`: build de la imagen, contenedor con modelo simulado, comprobación de que no corre
   como root y prueba de humo con `scripts/smoke.py`.

El CI no usa secretos: las claves de las corridas son de ejemplo y solo valen dentro del trabajo.
Hasta publicar el repositorio, el CI y el despliegue en Render están en NOT RUN. La publicación
requiere Manual Approval de la persona (`output/approved.txt`, que hoy no existe).

## Pruebas y resultados

Corridas del 2026-11-22, hechas por el supervisor de la fábrica con el modelo simulado salvo
donde se diga. Matriz completa de aceptación:
[doc/evidence/acceptance-matrix.md](doc/evidence/acceptance-matrix.md).

| Verificación | Estado | Resultado observado |
| --- | --- | --- |
| `unit` | PASS | 231 pruebas aprobadas, cobertura 96,24 %, código 0 |
| `qa` | PASS | [OK], pylint 10,00/10 |
| `contract --all` | PASS | 39/39 aprobados |
| `security` | PASS | 15 contratos de seguridad aprobados; escaneo de secretos sin hallazgos |
| `e2e` (corrida de I6) | PASS | 6/6 pruebas de Playwright en Chromium; no se repitió en esta sesión |
| `docker` (corrida de I6) | PASS | build; `/health` 200; `/docs` 200; `/ask` 401 sin clave y 200 con clave; usuario no root (uid 10001); no se repitió en esta sesión |
| `load` local (corrida de I6) | PASS | 10 concurrentes: 10/10 con 200, p50 19,4 ms, p95 22,1 ms, `request_id` únicos y registrados en el log ([evidencia](doc/evidence/load-local.md)); no se repitió en esta sesión |
| `evaluate` (SIMULADO, costo estimado no facturado) | PASS | baseline: calidad 100 %, 0,001541 USD estimados, 4609 tokens de entrada; palancas: calidad 100 %, 0,000267 USD estimados, 4039 tokens de entrada. Los tokens de entrada subieron respecto de I6 porque el Reviewer ahora recibe la evidencia de las herramientas (F3) |
| Revisión qa-style de I7 | NOT RUN | la revisa qa-style a continuación |
| `benchmark` (Cloudflare real) | NOT RUN | requiere `CF_ACCOUNT_ID` y `CF_API_TOKEN` de la persona |
| Trazas reales en LangSmith, con ruta de error | NOT RUN | requiere `LANGSMITH_API_KEY` de la persona |
| Publicación en GitHub (`marcotrejolemus/hr-assistant-v1`) | NOT RUN | Manual Approval pendiente: no existe `output/approved.txt` |
| Despliegue en Render | NOT RUN | requiere publicación previa y secretos en Render |
| `production <url>` y `load <url>` | NOT RUN | no hay URL todavía; requiere `SMOKE_API_KEY` |
| CI en GitHub Actions | NOT RUN | el repositorio no se ha publicado |
| Video y PR académico | NOT RUN | acciones de la persona; destino del PR pendiente de confirmar con el docente |

Las pruebas del producto viven en `tests/` (unitarias y Gherkin con `pytest-bdd`, archivos
`.feature` en `tests/features/`) y `e2e/` (Playwright). Los contratos de la fábrica viven fuera
del producto, en `verification/contract/`.

Notas sobre la tabla:

- La fila de la revisión qa-style de I7 se conserva como estaba al escribir la tabla. La
  vuelta 1 de esa revisión devolvió CAMBIOS; este README completo atiende su hallazgo
  bloqueante 1. La vuelta 2 sigue pendiente, así que esa fila no cuenta como PASS.
- Las filas `e2e`, `docker` y `load` local son de I6 y no se repitieron; conviene repetirlas
  antes de publicar.
- Hay una corrida real previa de `benchmark`, descrita en "Limitaciones". No cuenta como PASS
  ni como evidencia de I7: la fila `benchmark` sigue en NOT RUN.

## Limitaciones

- El proyecto no está listo: todo lo marcado NOT RUN depende de acciones de la persona
  (credenciales de Cloudflare y LangSmith, publicación aprobada, Render, PR y video).
- Dependencias de prueba en la imagen de producción: `requirements.txt` incluye `pytest`,
  `pytest-bdd` y `pytest-cov`, y la imagen las instala aunque solo corre la aplicación. Es una
  brecha frente a "usar valores seguros por omisión". Separarlas en un `requirements-dev.txt`
  queda pendiente; la persona decide si se corrige antes de publicar o se acepta como limitación.
- `doc/evidence/benchmark.md` es una corrida real previa a los cambios F1 a F3 de I7 (según
  ADR 0004; su fecha es 2026-11-23T03:13Z). Es histórica y no concluyente: no representa el
  código actual. En esa corrida, con el conjunto fijo de 8 casos, la calidad fue 0,5 en el
  baseline y 0,125 en la versión optimizada, con 23 contra 32 llamadas y 8690 contra 13406
  tokens de entrada. El encabezado "Ahorro estimado: 71.8 %" del archivo no es una optimización
  válida, porque la calidad empeoró; con calidad degradada la palanca no se usa (ADR 0006). La
  nueva corrida con el código de I7 (C3) sigue NOT RUN hasta que la persona la autorice y la
  ejecute con sus credenciales.
- La evidencia de costo es simulada y estimada; el costo facturado no está disponible desde el
  producto.
- Sin trazas reales en LangSmith, no hay evidencia de la ruta de error correlacionada con logs
  y métricas (NOT RUN).
- El límite de peticiones y las métricas son por proceso: con varias copias, el límite aplica a
  cada una.
- Las peticiones sin clave no tienen límite por IP; se mitiga con claves de 16 caracteres o más
  y con la auditoría `auth_denied`.
- El filtro de exfiltración es conservador y puede bloquear preguntas legítimas sobre "API key".
- El conjunto de evaluación es pequeño (8 casos) y los tokens simulados son una aproximación por
  palabras, no tokens reales del proveedor.
- La prueba de 10 solicitudes concurrentes es una meta propuesta del plan, no un umbral oficial.
- Con el plan gratuito de Render el servicio puede dormirse y la primera petición tardar hasta
  un minuto.
