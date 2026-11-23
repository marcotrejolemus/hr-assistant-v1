# Benchmark real: baseline contra optimizado

- Fecha (UTC): 2026-11-23T03:13:07+00:00
- Conjunto: verification/eval_set.json (8 casos), mismo historial
- Proveedor: Cloudflare Workers AI vía AI Gateway (`MODEL_PROVIDER=gateway`)
- Costo: estimado con spec/model_prices.json; facturado: no disponible (consultar el dashboard)

| Métrica | baseline | optimizado |
| --- | --- | --- |
| quality | 0.5 | 0.125 |
| errors | 0 | 0 |
| calls | 23 | 32 |
| input_tokens | 8690 | 13406 |
| output_tokens | 947 | 916 |
| p50_ms | 1978.3 | 1461.2 |
| p95_ms | 3026.3 | 1921.9 |
| cost_usd_estimated | 0.00338767 | 0.00095501 |

Ahorro estimado: 71.8%
