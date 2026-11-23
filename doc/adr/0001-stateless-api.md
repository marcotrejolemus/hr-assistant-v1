# 0001. API sin estado con historial enviado por el cliente

Estado: aceptado

Extendido por ADR 0004 y por el plan del reto (sección 2, "Concurrencia"): métricas y rate
limiter son estado de instancia creado en `create_app`, protegido con lock y sin datos de
peticiones. Extendido por ADR 0006: la caché del gateway queda apagada y prohibida en
producción.

## Contexto

El HR Assistant debe escalar corriendo más copias del proceso. Si la API guardara
conversaciones en memoria, cada copia tendría una vista distinta y haría falta
afinidad de sesión o un almacén compartido.

## Decisión

La API no guarda nada entre peticiones. El navegador conserva el historial y lo envía
en `history` en cada `POST /ask`. Los únicos datos del proceso son la configuración y
el directorio de empleados, ambos de solo lectura y cargados al arrancar.
`GET /health` devuelve el `pid` para comprobar qué copia respondió.

## Consecuencias

- Escalar es correr más copias detrás de un balanceador, sin coordinación.
- El cliente controla el historial: hay que validarlo (roles `user|assistant`) y no
  confiar en él para nada sensible.
- Las peticiones crecen con la conversación; si hace falta, se limitará su tamaño.
- No hay variables globales mutables: cualquier caché futura requiere un ADR nuevo.
