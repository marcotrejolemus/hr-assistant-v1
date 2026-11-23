# 0003. Inyección de dependencias en create_app y configuración validada al arrancar

Estado: aceptado

Extendido por ADR 0004 y 0005: `create_app` recibe además, por palabra clave, `clock`,
`log_sink` y `trace_client_factory`, y `load_settings` aplica las reglas de compliance con
`ENVIRONMENT=production`. Extendido por ADR 0006: un modelo sin precio impide arrancar.

## Contexto

QA.md exige inyección de dependencias y comportamiento determinista. Las pruebas
necesitan cambiar el modelo, el directorio y el tope del bucle sin variables de
entorno globales. Un valor de configuración inválido no debe descubrirse en la
primera petición.

## Decisión

`create_app(settings=None, model=None, directory=None)` recibe sus dependencias; si
faltan, las construye desde el entorno con `load_settings`. `main.py` expone
`app = create_app()` para uvicorn. `load_settings` valida todos los valores y lanza
`ValueError` con un mensaje claro, de modo que el proceso no arranca con
configuración inválida. Nada en el producto lee el entorno ni la hora fuera de este
punto.

## Consecuencias

- Las pruebas usan `TestClient(create_app(...))` con dependencias falsas, sin
  procesos ni red.
- Importar `app.main` falla de inmediato si el entorno es inválido; es lo buscado,
  pero las pruebas deben importar `create_app` con un entorno limpio.
- Agregar una dependencia nueva implica un parámetro nuevo en `create_app`.
