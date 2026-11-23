# 0002. Modelo detrás de una interfaz y protocolo JSON

Estado: aceptado

Extendido por ADR 0004: la interfaz conserva su nombre y pasa a async,
`complete(messages, *, model, max_tokens)`; existe además `GatewayLanguageModel`
(Cloudflare AI Gateway). Extendido por ADR 0006: el modelo lo elige el router de costo.

## Contexto

En esta sesión solo hay un modelo simulado, pero después se conectarán modelos
reales. El agente no debe cambiar cuando cambie el proveedor, y las pruebas deben ser
deterministas, sin red ni costo.

## Decisión

`llm.py` define la interfaz `LanguageModel` con un único método
`complete(messages)`, que devuelve el texto JSON de la respuesta y los tokens de
entrada y salida. El modelo responde siempre un objeto JSON: `{"tool", "args"}` o
`{"answer"}`. `build_model(settings, directory)` elige la implementación según
`MODEL_PROVIDER`; hoy solo existe `FakeLanguageModel`, que aplica las reglas del spec
y recibe la lista de departamentos por constructor.

## Consecuencias

- Agregar un proveedor real es una clase nueva y una rama en `build_model`, sin tocar
  `agent.py`.
- Las pruebas inyectan modelos guionizados para cubrir casos difíciles (JSON inválido,
  herramienta desconocida, tope).
- El agente debe tolerar respuestas mal formadas: las trata como error dentro del
  bucle, nunca como excepción hacia la API.
- El conteo de tokens del modelo simulado es aproximado (palabras) y no sirve para
  estimar costos reales.
