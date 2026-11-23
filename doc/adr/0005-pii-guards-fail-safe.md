# 0005. Guardas deterministas de PII e inyección, con falla segura

Estado: aceptado (2026-11-22)

## Contexto

`spec/05-reto.md` exige detectar PII antes de enviar texto al proveedor y antes de
responder, bloquear o redactar según una política explícita, probar inyección y
exfiltración, auditar decisiones sin datos sensibles y fallar de forma segura. Un LLM no
puede ser el control final: puede fallar, alucinar o ser manipulado.

## Decisión

- `pii.py` detecta con patrones deterministas: email, teléfono (10 dígitos, con o sin +52),
  CURP, RFC y tarjeta (Luhn). Se reemplaza por `[REDACTED:<tipo>]` y se devuelven los tipos
  en `redactions`. No se redactan ids `EMP-NNNN`, fechas ISO ni datos del directorio
  sintético.
- Input Guard: la redacción ocurre antes del proveedor, de los logs y de las trazas. La
  inyección o exfiltración (pregunta o historial, español e inglés, normalizado sin acentos)
  responde `400 {"detail": "request blocked by policy"}`.
- Output Guard decide siempre: redacta PII nueva y cambia por la respuesta segura fija
  cualquier salida con secretos, prompt de sistema o tamaño excesivo.
- Auditoría en líneas JSON `"event": "audit"` con `request_id`, `client`, `action` y
  `outcome`; nunca claves, preguntas, respuestas ni PII.
- Falla segura: sin `API_KEYS` todo es 401; no existe bypass de autenticación; en
  `ENVIRONMENT=production` el producto se niega a arrancar si la configuración es insegura.

## Consecuencias

- Controles reproducibles y probables sin red, con pruebas positivas y negativas.
- Habrá falsos positivos (por ejemplo, preguntar por una "API key") y falsos negativos
  (PII en formatos no previstos); las listas se mantienen en código y se prueban.
- La política se documenta en `doc/compliance-checklist.md` y en el README.
