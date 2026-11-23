# Lista de seguridad y compliance

Cada regla de seguridad y compliance del HR Assistant (`spec/04-production.md`, `spec/05-reto.md`
sección 5 y la sección 6 del plan), dónde está en el código y cómo se comprueba. Las rutas son relativas a
`product/`; los contratos están en `verification/contract/`.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| `API_KEYS` tiene la forma `cliente:clave,cliente2:clave2`; una clave por cliente | `app/security.py` (`parse_api_keys`), `app/config.py` (`load_settings`) | `tests/test_security.py::test_api_keys_are_read_per_client_and_hidden_from_repr` |
| Una `API_KEYS` mal formada impide arrancar; el error dice la entrada y su largo, nunca el valor | `app/security.py` (`parse_api_keys`, `_malformed`) | `tests/test_security.py::test_malformed_api_keys_name_the_entry_and_length_but_never_the_value`; `test_contract_04.py::test_a_broken_api_keys_never_leaks_the_key` |
| Las claves no salen en `repr` de la configuración | `app/config.py` (`Settings.api_keys` con `repr=False`) | `tests/test_security.py::test_api_keys_are_read_per_client_and_hidden_from_repr` |
| `POST /ask` y `GET /metrics` exigen `X-API-Key`; sin clave o con una inválida responden `401 {"detail": "invalid or missing API key"}` | `app/main.py` (`_build_client_dependency`, `APIKeyHeader(auto_error=False)`) | `tests/features/security.feature` (claves faltantes o equivocadas, métricas); `test_contract_04.py` (401); `test_contract_05_security.py::test_metrics_need_a_key` |
| Las claves se comparan en tiempo constante | `app/security.py` (`find_client`, `_same_key` con `hmac.compare_digest`) | Revisión de código; los escenarios 401 y 200 de `tests/features/security.feature` |
| `/`, `/health`, `/docs` y `/openapi.json` no piden clave | `app/main.py` (rutas sin la dependencia) | `tests/features/security.feature` (páginas públicas); `test_contract_04.py::test_health_and_page_need_no_key` |
| OpenAPI declara el esquema `apiKey` en el encabezado `X-API-Key` | `app/main.py` (`APIKeyHeader`) | `tests/test_security.py::test_openapi_declares_the_api_key_header`; `test_contract_05_security.py::test_openapi_declares_the_api_key_header` |
| Sin bypass: con `API_KEYS` vacía, todo es 401 | `app/security.py` (`find_client` devuelve `None`), `app/main.py` | `tests/features/security.feature` (sin claves configuradas) |
| Más de `RATE_LIMIT_PER_MINUTE` peticiones por cliente y minuto: `429 {"detail": "rate limit exceeded"}` con `Retry-After` | `app/security.py` (`RateLimiter`), `app/main.py` (dependencia, reloj inyectado `clock.monotonic`) | `tests/test_security.py` (clientes separados, ventana con reloj fijo); `tests/features/security.feature` (tercera petición); `test_contract_04.py::test_too_many_requests_returns_429_with_retry_after` |
| `RATE_LIMIT_PER_MINUTE` es un entero >= 1 | `app/config.py` (`_positive_int`) | `tests/test_security.py::test_rate_limit_must_be_a_positive_integer` |
| Producción: no arranca con `MODEL_PROVIDER=fake` | `app/security.py` (`enforce_production_rules`) | `tests/test_security.py::test_production_refuses_to_start_with_an_unsafe_setting[fake_model]`; `test_contract_04.py::test_production_refuses_the_fake_model` |
| Producción: no arranca con `API_KEYS` vacía o con una clave de menos de 16 caracteres | `app/security.py` (`enforce_production_rules`) | `tests/test_security.py::test_production_refuses_to_start_with_an_unsafe_setting[no_keys, short_key]` |
| Producción: con trazas encendidas, `HIDE_INPUTS` y `HIDE_OUTPUTS` deben valer `true` | `app/security.py` (`enforce_production_rules`) | `tests/test_security.py::test_production_refuses_to_start_with_an_unsafe_setting[inputs_shown, outputs_shown]` |
| Producción: no arranca si hay algún `FAKE_*` definido | `app/security.py` (`enforce_production_rules`) | `tests/test_security.py::test_production_refuses_to_start_with_an_unsafe_setting[fake_switch_defined]` |
| Producción: no arranca con `CACHE_TTL_SECONDS > 0` (ADR 0006) | `app/config.py` (`_environment`) | `tests/test_costs.py::test_gateway_cache_is_refused_in_production` |
| Una configuración de producción segura sí arranca | `app/config.py`, `app/security.py` | `tests/test_security.py::test_safe_production_settings_start` |
| La exfiltración y la inyección (en español y en inglés) dan `400 request blocked by policy` | `app/guards.py` (`InputGuard`, `classify_attack`), `app/main.py` | `tests/features/security.feature`; `test_contract_05_security.py::test_exfiltration_and_injection_are_blocked` |
| Las herramientas son de solo lectura: pedir un cambio no altera nada | `app/agent.py`, `app/directory.py` | `tests/features/security.feature` (borrar un empleado); `test_contract_05_security.py::test_directory_tools_are_read_only` |
| Una herramienta rechazada (desconocida o con argumentos inválidos) no se ejecuta y deja auditoría `tool_denied` (`outcome=denied`) con `tool` = nombre permitido o `unknown`, sin argumentos ni el nombre desconocido, con `request_id` y `client`; no hay `tool_call` | `app/agent.py` (`_execute`, `observe_denied`), `app/observability.py` (`RequestObserver.tool_denied`), `app/supervisor.py` | `tests/test_security.py::test_denied_tool_requests_are_audited_without_the_model_arguments`; `tests/test_agent.py::test_tool_arguments_outside_the_allowed_shape_are_denied` |
| El Directory Specialist manda en cada llamada un único prompt de sistema fijo (protocolo JSON y las dos herramientas), en español y sin secretos, configuración ni datos del directorio; no cuenta en `HISTORY_WINDOW`. Su marcador `SPECIALIST_MARKER`, igual que `REVIEWER_MARKER`, hace que el Output Guard cambie la salida por la respuesta segura | `app/agent.py` (`SPECIALIST_PROMPT`, `SPECIALIST_MARKER`, `run`), `app/guards.py` (`OutputGuard._must_block`) | `tests/test_agent.py::test_every_specialist_call_starts_with_the_system_prompt`; `tests/test_guards.py::test_system_prompt_marker_in_the_draft_is_treated_as_a_leak` |
| La PII de la entrada se redacta antes del proveedor, de los logs y de las trazas | `app/pii.py`, `app/guards.py` (`InputGuard`) | `tests/test_security.py::test_redacted_pii_is_audited_by_type_only`; `tests/test_pii.py` |
| Auditoría `auth_denied`, `rate_limited`, `policy_block` (con categoría), `pii_redacted` (solo tipos), `review_verdict` y `output_blocked`, con `request_id` y `client` | `app/main.py` (dependencia y `ask`), `app/supervisor.py` (`_audit_decisions`), `app/observability.py` (`RequestObserver.audit`) | Pruebas de auditoría en `tests/test_security.py`; `test_contract_05_security.py::test_audit_records_decisions_without_secrets_or_pii` |
| Los eventos `request` y `agent_run` llevan el nombre del cliente; la traza lo lleva en metadatos | `app/main.py` (middleware), `app/observability.py` | `tests/test_security.py::test_request_events_carry_the_client_name` |
| El log nunca contiene una clave (válida o inválida), PII ni el texto de la pregunta | `app/main.py`, `app/observability.py` (solo campos de conjunto cerrado) | `tests/test_security.py` (auditorías); `test_contract_05_security.py::test_audit_records_decisions_without_secrets_or_pii` |
| Página: campo `data-testid="api-key"` de tipo contraseña; la clave va en `sessionStorage` (nunca en `localStorage`) y se envía en `X-API-Key`; muestra «Clave inválida» y «Demasiadas preguntas; espera N segundos» | `app/static/index.html` | `tests/test_security.py::test_home_page_keeps_the_key_in_session_storage_in_a_password_field`; `test_contract_04.py::test_health_and_page_need_no_key` |
| No hay secretos ni archivos sensibles en `product/` | `.env.example` solo trae nombres | `uv run python -m verification security` (escáner de secretos) |
| Las dependencias tienen versiones fijas | `requirements.txt` (todas con `==`, incluida `langsmith`) | Revisión de `requirements.txt` |

Limitaciones conocidas:

- El límite de peticiones y las métricas son por proceso. Con varias copias, el límite aplica a cada copia.
- Las peticiones sin clave no tienen límite por IP. Se mitiga con claves de 16 caracteres o más y con la
  auditoría `auth_denied`.
- El filtro de exfiltración es conservador: puede bloquear preguntas legítimas sobre «API key».
- `pytest`, `pytest-bdd` y `pytest-cov` se instalan en la imagen de producción (hallazgo 5 de qa-style);
  separarlas en un `requirements-dev.txt` queda pendiente.
