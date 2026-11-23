# La fábrica que construyó el HR Assistant v1

La **fábrica** es el conjunto de agentes de Claude Code que escribió el plan, las pruebas, el
código, la configuración y esta documentación. No atiende peticiones y no se despliega: vive
en el repositorio de trabajo (`.claude/agents/`, `.claude/skills/factory-reto/`, `hooks/`,
`verification/`, `scripts/`). El **runtime** (lo que atiende `POST /ask`) se describe en
[architecture.md](architecture.md); no hay que confundir sus agentes LLM (Directory
Specialist y Reviewer) con los agentes de la fábrica.

## Diagrama

```mermaid
flowchart TD
    P(["Persona: dirige, aprueba y comprueba"])
    P -->|"/factory-reto I1 ... I7, un incremento a la vez"| SUP
    SUP["Supervisor de Claude Code (skill factory-reto): delega, no escribe product/"]

    subgraph AG["Agentes de la fábrica (.claude/agents/)"]
        ARC["architect: plan, ADR, README, doc/"]
        QAU["qa-unit: pruebas primero (rojo)"]
        DEV["developer: I1"]
        OBS["observability: I2"]
        CST["costs: I3"]
        SEC["security: I4 y correcciones de I6"]
        DEP["deploy: Docker, Render, CI, smoke"]
        QAE["qa-e2e: Playwright"]
        QAS["qa-style: revisión QA.md"]
        TRI["triage: decide dueño o persona"]
    end

    SUP --> ARC
    SUP --> QAU
    SUP --> DEV
    SUP --> OBS
    SUP --> CST
    SUP --> SEC
    SUP --> DEP
    SUP --> QAE
    SUP --> QAS
    SUP -->|"tras 2 correcciones fallidas"| TRI

    subgraph HK["Hooks de Claude Code"]
        PERM["PreToolUse hooks/permissions.py: carpetas por agente, nadie lee archivos de secretos, aprobación intocable, publicar solo con publish.py"]
        LOG["PostToolUse hooks/activity_log.py: bitácora output/activity.jsonl"]
    end

    AG -.->|"cada herramienta"| PERM
    AG -.->|"cada herramienta"| LOG
    LOG -.-> PIPE["scripts/pipeline.py: dibuja el pipeline"]

    subgraph GT["Compuertas (verification/, el código decide por código de salida)"]
        G1["unit, contract, qa"]
        G2["evaluate, security"]
        G3["e2e, docker, load"]
        G4["contract --all sin PENDING"]
    end

    ARC -->|"plan.md"| HP{"Persona aprueba el plan (máx. 2 rechazos)"}
    HP --> QAU
    QAU --> G1
    DEV --> G1
    OBS --> G1
    CST --> G2
    SEC --> G2
    DEP --> G3
    QAE --> G3
    QAS -->|"APROBADO o CAMBIOS (máx. 2 vueltas)"| SUP
    GT -->|"código 0: siguiente incremento con autorización"| SUP
    GT -->|"fallo: máx. 2 correcciones"| SUP

    SUP --> G4
    G4 --> RM["Persona: release_manifest.py dueño/repo, revisa archivos y sha256"]
    RM -->|"--aprobar en su terminal"| APR[("output/approved.txt: aprobación de un solo uso")]
    APR --> PUB["scripts/publish.py --remote: vuelve a correr contract --all, consume la aprobación, sin --force"]
    PUB --> GH[("GitHub: repositorio existente")]
    GH -->|"CI 4 etapas pasa"| RND[("Render: Blueprint render.yaml")]
```

## Piezas

| Pieza | Qué hace | Dónde |
| --- | --- | --- |
| Supervisor | Lanza a cada agente con el plan aprobado, corre las compuertas una por una y decide solo con códigos de salida y la primera línea de `output/qa-review.md` y `output/triage.md`. Nunca escribe en `product/`. | `.claude/skills/factory-reto/SKILL.md` |
| architect | Plan, ADR, `architecture.md`, `factory.md`, evidencia y README. | `.claude/agents/architect.md` |
| qa-unit | Escribe primero las pruebas Gherkin y unitarias; la suite debe quedar en rojo. | `.claude/agents/qa-unit.md` |
| developer, observability, costs, security | Un solo dueño de `product/app/` por incremento (I1 a I4). | `.claude/agents/` |
| deploy y qa-e2e | En paralelo en I5; ninguno toca `product/app/`. | `.claude/agents/` |
| qa-style | Revisa contra `QA.md` y escribe `output/qa-review.md` (`APROBADO` o `CAMBIOS`). | `.claude/agents/qa-style.md` |
| triage | Tras 2 correcciones fallidas, nombra al dueño o a `persona`; no corrige. | `.claude/agents/triage.md` |
| Hook de permisos | Bloquea (código 2) escrituras fuera de las carpetas de cada agente, cualquier lectura de archivos de entorno con secretos (solo las plantillas públicas quedan libres), todo toque de la aprobación, `git push` y `gh` directos, y `publish.py` encadenado o sin aprobación válida para su destino. Falla cerrado ante eventos malformados. | `hooks/permissions.py` |
| Bitácora | Una línea JSON por herramienta usada (quién, qué, resultado). | `hooks/activity_log.py`, `scripts/pipeline.py` |
| Compuertas | `uv run python -m verification <paso>`: 0 pasa, 3 es NOT RUN (nunca PASS), otro código falla. | `verification/` |
| Aprobación de publicación | La persona corre `release_manifest.py <dueño/repo>` (manifiesto con `sha256` por archivo y escaneo de secretos) y, si está de acuerdo, `--aprobar` en una terminal interactiva. `publish.py` valida destino, origen y `sha256` actuales, consume la aprobación una sola vez de forma atómica y nunca usa `--force`. | `scripts/release_manifest.py`, `scripts/publish.py` |

## Topes

- 2 rechazos del plan, 2 correcciones por compuerta y 2 vueltas de qa-style; después, triage
  o la persona.
- Ningún agente baja un umbral, borra una prueba ni convierte un fallo en omitida.
- Ningún commit, push, PR ni despliegue sin autorización explícita de la persona para ese
  paso.
