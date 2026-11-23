# Matriz de aceptación del reto M4 (Definition of Done, `spec/05` sección 8)

- Fecha de corte: 2026-11-22. Corridas hechas por el supervisor de la fábrica con el modelo
  simulado (`MODEL_PROVIDER=fake`), salvo donde se indique.
- Estados: **PASS** (comando con código 0 o resultado observado), **FAIL**, **NOT RUN** (no se
  ha corrido; se da el motivo). NOT RUN nunca cuenta como PASS.
- **El proyecto NO está listo**: quedan requisitos obligatorios en NOT RUN (los de I7: benchmark
  real, LangSmith, publicación, Render, humo, carga remota, CI, PR y video). La revisión de
  qa-style de I7 ya se hizo (APROBADO, vuelta 2 de 2, con 3 menores abiertos).
- Estado local de I7: en esta sesión se corrieron `qa`, `unit`, `contract --all`, `evaluate` y
  `security`. Las filas de `e2e`, `docker` y carga local conservan las cifras de I6 y lo
  indican; no se volvieron a correr en esta sesión.
- Los dictámenes de qa-style de I6 son históricos: el de I6 está en `output/qa-review-i6.md`
  (carpeta `output/` ignorada por Git, no versionable) y el de I7 en `output/qa-review.md`.
- La publicación sigue con Manual Approval: no existe `output/approved.txt`.
- Las metas técnicas de esta matriz (por ejemplo 10 solicitudes concurrentes) son propuestas
  del plan, no umbrales oficiales de calificación.
- Los comandos se corren desde la raíz del repositorio de la fábrica con
  `uv run python -m verification <paso>`.

## Calidad de la fábrica (I7 local)

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| Pruebas unitarias y Gherkin con cobertura >= 80 % | PASS | `verification unit` | 231 pruebas aprobadas, cobertura 96,24 %, código 0 | salida de la corrida; `product/tests/` |
| Estilo `QA.md` (pylint, 88 columnas) | PASS | `verification qa` | [OK], pylint 10,00/10; la advertencia W0632 de `product/tests/test_reviewer_evidence.py` quedó resuelta | salida de la corrida |
| Contratos completos sin PENDING | PASS | `verification contract --all` | 39/39 aprobados | `verification/contract/` |
| Revisión de estilo qa-style de I7 | PASS | revisión de qa-style | APROBADO en la vuelta 2 de 2 de I7 (sin bloqueantes ni mayores; 3 menores abiertos, ver Pendientes) | `output/qa-review.md` (`output/` no se versiona: el dictamen vive en la fábrica) |
| Revisión de estilo qa-style de I6 (histórica) | PASS (histórica) | revisión de qa-style (2026-11-22) | APROBADO en la vuelta 2 de I6; la vuelta 1 ya no se conserva y no es comprobable | `output/qa-review-i6.md` |

## A. Arquitectura y despliegue

Las filas A1 a A9 de Docker y carga local son cifras de I6: no se volvieron a correr en esta
sesión.

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| A1. Build Docker exitoso | PASS (corrida de I6) | `verification docker` | build correcto | salida de la corrida de I6; `product/Dockerfile` |
| A2. Contenedor con `GET /health` 200 | PASS (corrida de I6) | `verification docker` | 200 | salida de la corrida de I6 |
| A3. Swagger accesible | PASS (corrida de I6) | `verification docker` | `/docs` 200 | salida de la corrida de I6 |
| A4. Sin credenciales: 401 | PASS | `contract --all` (`test_contract_04.py`); `verification docker` (I6) | `/ask` sin clave 401 | salida de la corrida |
| A5. Consulta autenticada exitosa (modelo simulado, contenedor local) | PASS (corrida de I6) | `verification docker` | `/ask` con clave 200 | salida de la corrida de I6 |
| A6. Consulta real autenticada con Cloudflare | NOT RUN | `verification benchmark` o `production <url>` con `MODEL_PROVIDER=gateway` | requiere `CF_ACCOUNT_ID`, `CF_API_TOKEN` y la URL de Render (acciones de la persona, I7) | pendiente |
| A7. Usuario no root | PASS (corrida de I6) | `verification docker` | uid 10001 | `product/Dockerfile` (`USER 10001:10001`) |
| A8. Escucha en el puerto de la plataforma | PASS (corrida de I6) | `verification docker` (arranca con `PORT=8000`) | contenedor responde en el puerto configurado | `product/Dockerfile` (`${PORT:-8000}`) |
| A9. 10 solicitudes concurrentes (local) con tiempos, errores y `request_id` | PASS (corrida de I6) | `verification load` | 10/10 con 200, p50 19,4 ms, p95 22,1 ms, 0 errores, `request_id` únicos y presentes en el log | `product/doc/evidence/load-local.md` |
| A10. 10 solicitudes concurrentes contra la URL publicada | NOT RUN | `verification load <url>` con `SMOKE_API_KEY` | no hay despliegue todavía (I7) | pendiente |
| A11. Concurrencia sin estado mutable inseguro, timeouts y límites | PASS | `verification unit` y `contract --all` | pruebas de peticiones concurrentes independientes, timeout con modelo lento, topes de llamadas y tokens pasan | `product/tests/test_supervisor.py`, `product/doc/architecture.md` |
| A12. Respuesta predecible si el proveedor cae | PASS | `contract --all` (`test_contract_05.py`) | 502 `model unavailable` con `request_id` | `product/doc/architecture.md` (decisiones de falla) |
| A13. Artefactos: `Dockerfile`, `.dockerignore`, `.gitignore`, `.env.example` sin valores secretos, `render.yaml`, CI | PASS | revisión de archivos; `verification security` (escaneo de secretos) | presentes; escaneo de secretos sin hallazgos | `product/` |
| A14. Versiones reproducibles de dependencias | PASS | revisión de `product/requirements.txt` | todas con `==` | `product/requirements.txt` |
| A15. CI de 4 etapas en GitHub Actions | NOT RUN | corrida del flujo `ci` en GitHub | el repositorio no se ha publicado (I7) | `product/.github/workflows/ci.yml` |

## O. Observabilidad

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| O1. `request_id` generado o respetado y devuelto | PASS | `contract --all` (`test_contract_02.py`); `verification load` (I6) | presente en encabezado y cuerpo; 10 `request_id` únicos en la carga de I6 | `product/doc/evidence/load-local.md` |
| O2. Logs JSON estructurados (ts, request_id, etapa, duración, estado, errores sanitizados) | PASS | `verification unit`; `contract --all` | pruebas de campos del log con reloj fijo pasan | `product/tests/test_observability.py` |
| O3. Tokens y costo por request, modelo y estrategia; estimado vs facturado | PASS | `contract --all` (`test_contract_03.py`) | `cost_usd`, `model`, `route` en `/ask`; `cost_billed: "not_available"` en `/metrics` | `product/app/metrics.py` |
| O4. Métricas protegidas y sin alta cardinalidad | PASS | `contract --all` (`test_contract_05_security.py::test_metrics_need_a_key`) | `/metrics` sin clave da 401; etiquetas de conjuntos cerrados | `product/doc/compliance-checklist.md` |
| O5. Fallo de telemetría no rompe la respuesta | PASS | `verification unit` | pruebas de cliente de trazas que falla pasan | `product/tests/test_observability.py` |
| O6. Trazas reales en LangSmith (proyecto `hr-assistant-v1`) con padre/hijo | NOT RUN | consultas con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY` | requiere la clave de LangSmith de la persona (I7) | pendiente |
| O7. Ruta de error controlado trazada y correlacionada con logs y métricas | NOT RUN | consulta con error controlado y trazas reales | requiere LangSmith real (I7) | pendiente |
| O8. Evidencia sanitizada de LangSmith | NOT RUN | captura sanitizada | depende de O6 y O7 | pendiente |

## C. Costos

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| C1. Al menos una estrategia implementada (routing, ventana, tope de salida) | PASS | `verification unit`; `contract --all` (`test_contract_03.py`) | pruebas de router, ventana y `MODEL_MAX_TOKENS` pasan | `product/app/router.py`, ADR 0006 |
| C2. Baseline vs optimizado, mismo conjunto y condiciones (SIMULADO, costo estimado no facturado) | PASS (simulado) | `verification evaluate` | baseline: calidad 100 %, 0,001541 USD estimados, 4609 tokens de entrada; palancas: calidad 100 %, 0,000267 USD estimados, 4039 tokens de entrada. Los tokens de entrada subieron respecto de I6 porque el Reviewer ahora recibe la evidencia de las herramientas (F3) | salida de la corrida; `product/doc/evidence/evaluate-simulated.md` |
| C3. Baseline vs optimizado con modelos reales | NOT RUN | `verification benchmark` | requiere `CF_ACCOUNT_ID` y `CF_API_TOKEN` en la terminal de la persona (I7). Existe una corrida real previa a F1-F3 en `product/doc/evidence/benchmark.md`: es histórica y no concluyente (el ahorro de 71,8 % vino con la calidad bajando de 0,5 a 0,125), no representa el código de I7 y no cuenta como PASS. C3 sigue NOT RUN hasta repetirla tras F3 | `product/doc/evidence/benchmark.md` (histórica) |
| C4. Costo estimado separado de facturado; tarifas con fecha y unidad | PASS | revisión de `/metrics` y de `spec/model_prices.json` | facturado: no disponible; tarifas en USD por millón de tokens, revisadas 2026-11-04 | `product/doc/evidence/evaluate-simulated.md` |
| C5. Caché sin aislamiento evitada | PASS | `verification unit` (`test_gateway_cache_is_refused_in_production`) | caché apagada por omisión y prohibida en producción | ADR 0006 |

## S. Seguridad

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| S1. Credencial ausente o inválida | PASS | `verification security`; `contract --all` | 401 `invalid or missing API key` | `product/doc/compliance-checklist.md` |
| S2. Input inválido | PASS | `contract --all`; `verification unit` | 422 sin llamar al modelo | `product/tests/` |
| S3. Rate limiting | PASS | `verification security` (`test_contract_04.py`) | 429 `rate limit exceeded` con `Retry-After` | `product/doc/compliance-checklist.md` |
| S4. PII de entrada y de salida | PASS | `verification security`; `verification unit` | redactada por tipo; auditoría solo con tipos | `product/tests/test_pii.py` |
| S5. Prompt injection y exfiltración | PASS | `verification security` (`test_contract_05_security.py`) | 400 `request blocked by policy` | `product/doc/compliance-checklist.md` |
| S6. Autorización de herramientas | PASS | `verification security`; `verification unit` | herramientas de solo lectura; herramienta rechazada auditada como `tool_denied` sin argumentos | `product/doc/compliance-checklist.md` |
| S7. Auditoría sin datos sensibles | PASS | `verification security` (`test_audit_records_decisions_without_secrets_or_pii`) | eventos `audit` sin claves, PII ni texto | `product/doc/compliance-checklist.md` |
| S8. Compliance en producción (sin bypass, se niega a arrancar si es inseguro) | PASS | `verification unit`; `contract --all` (`test_contract_04.py`) | reglas de `ENVIRONMENT=production` probadas | `product/doc/compliance-checklist.md` |
| S9. Secretos ausentes de código, configuración y evidencia del producto | PASS | `verification security` (escaneo de secretos) | 15 contratos de seguridad aprobados; escaneo de secretos sin hallazgos | salida de la corrida |
| S10. Secretos ausentes de trazas reales y logs de la plataforma | NOT RUN | revisión de LangSmith y de los logs de Render | no hay trazas reales ni despliegue (I7) | pendiente |

## Entrega

| Criterio | Estado | Comando o procedimiento | Resultado observado | Evidencia |
| --- | --- | --- | --- | --- |
| E1. Código funcional, Docker y configuración reproducible | PASS parcial: local de I7 y Docker de I6 | Corrido en I7: `unit`, `contract --all`, `qa`, `security`. Heredado de I6 (no repetido): `e2e` y `docker` | I7: 231 pruebas, 39/39 contratos, estilo y seguridad pasan. I6: e2e 6/6 Playwright en Chromium y build Docker, que no se repitieron con el código de I7 | `product/` |
| E2. README con arquitectura, agentes, decisiones, setup, comandos, API, variables, seguridad, costos, trade-offs, pruebas y limitaciones | PASS | revisión de qa-style de I7 sobre el README | qa-style de I7 verificó que el README tiene todas las secciones de `spec/05-reto.md`. Dictamen de I7: APROBADO en la vuelta 2 de 2. Histórico de I6: APROBADO (`output/qa-review-i6.md`) | `product/README.md`; `output/qa-review.md` (I7; `output/` no se versiona); `output/qa-review-i6.md` (histórico) |
| E3. Diagramas de fábrica y de runtime diferenciados | PASS (I7) | revisión de qa-style de I7 | qa-style de I7 verificó que `architecture.md` recoge la evidencia del Reviewer (el Reviewer recibe la evidencia de las herramientas). Histórico de I6: APROBADO, runtime y fábrica separados y coincidían con el código | `product/doc/factory.md`, `product/doc/architecture.md`; `output/qa-review.md` (I7); `output/qa-review-i6.md` (histórico) |
| E4. Evidencia sanitizada en ubicación versionable | NOT RUN (parcial) | revisión de `product/doc/evidence/` | hay carga local (I6), `evaluate` simulado de I7 y esta matriz; `benchmark.md` es una corrida real previa a F1-F3, histórica y no concluyente, que no cuenta como PASS de I7; faltan LangSmith, `benchmark` repetido tras F3, despliegue y carga remota (I7) | `product/doc/evidence/` |
| E5. Publicación en GitHub (`marcotrejolemus/hr-assistant-v1`) | NOT RUN | `release_manifest.py <dueño/repo>`, `--aprobar` (persona) y `publish.py <dueño/repo> --remote <dueño/repo>` | Manual Approval pendiente: no existe `output/approved.txt` (I7) | pendiente |
| E6. Despliegue en Render | NOT RUN | Blueprint `render.yaml`; secretos en Render > Environment | requiere publicación previa y acciones de la persona (I7) | pendiente |
| E7. Prueba de humo contra la URL | NOT RUN | `verification production <url>` con `SMOKE_API_KEY` | no hay URL todavía (I7) | pendiente |
| E8. PR académico | NOT RUN | PR desde fork o rama propia | destino pendiente de confirmar con el docente (I7) | pendiente |
| E9. Video de máximo cinco minutos | NOT RUN | grabación por la persona | depende del despliegue y de las trazas reales (I7) | pendiente |
| E10. Etiqueta `Share-OK` | NOT RUN | decisión del alumno | opcional; no decidida | pendiente |

## Pendientes que se elevan a la persona

1. Todo lo marcado NOT RUN de I7: `benchmark` real repetido tras F3, LangSmith real con ruta
   de error, publicación aprobada, Render, prueba de humo y carga contra la URL, CI en GitHub,
   PR académico y video.
2. Confirmar el destino del PR académico con el docente.
3. La revisión de qa-style de I7 ya se hizo: APROBADO en la vuelta 2 de 2, sin bloqueantes ni
   mayores. Quedan registrados 3 menores:
   - (a) `product/doc/evidence/benchmark.md` no tiene nota propia en su encabezado que diga
     que es previa a F1-F3 y que la calidad bajó de 0,5 a 0,125. Abierto.
   - (b) Las filas 27 y 28 de esta matriz y la línea 43 de `product/doc/compliance-checklist.md`
     citan rutas de `output/`, que no es versionable. Abierto.
   - (c) El menor de la viñeta falsa del README (líneas 387 a 389) quedó resuelto: la viñeta
     se eliminó.
4. Decidir si se corrige el hallazgo de dependencias de prueba incluidas en la imagen de
   producción (separarlas en un `requirements-dev.txt`) antes de publicar o si se acepta
   como limitación documentada.
5. Decidir si se repiten `e2e`, `docker` y `load` con el código de I7 antes de publicar.
