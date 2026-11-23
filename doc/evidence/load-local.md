# Prueba de carga (local)

- Fecha (UTC): 2026-11-23T02:31:50+00:00
- Concurrencia: 10 solicitudes a la vez a `POST /ask`
- Latencia p50: 19.4 ms; p95: 22.1 ms
- request_id registrados en logs: sí

| # | Estado | ms | request_id |
| --- | --- | --- | --- |
| 0 | 200 | 19.4 | 10c8e74e-97fd-46aa-8e3a-b6f018d3378e |
| 1 | 200 | 20.9 | 49fd2a0c-e036-4b8d-977e-c76ebfaa9a44 |
| 2 | 200 | 22.1 | 7ce71035-f48c-493b-935f-109e1fafb9d8 |
| 3 | 200 | 18.3 | 50e84d3c-7560-4b12-be44-b381e100707f |
| 4 | 200 | 15.9 | 1d160207-9321-4b4e-bf50-825b258a4ec5 |
| 5 | 200 | 20.1 | 4bb286ac-124e-4ec7-b91e-dc90d015f302 |
| 6 | 200 | 19.2 | b6f25510-7b19-40d1-bf24-e440be9a5f02 |
| 7 | 200 | 20.6 | 97fcd789-3ea3-4665-b318-8fcb71c8d90a |
| 8 | 200 | 20.4 | c814b769-909f-4caf-b479-c899dfea02d2 |
| 9 | 200 | 18.8 | 232ecdd4-3014-4659-ba45-da13f01e10de |
