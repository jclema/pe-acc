# Sanciones OSCE: ingesta por API

API opt-in basada en `feat/data`: descarga `sancionados.csv` e
`inhabilitaciones_judiciales.csv` desde [OSCE/OECE PNDA](https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269).
No incluye multas. Descarga comprobada el 2026-10-01; no acredita corte ni licencia.
`PE_OSCE_SOURCE_MODE=file` es el predeterminado. Configuración: `PE_OSCE_SOURCE_MODE=api`,
`PE_OSCE_CONFLUENCE_BASE_URL` y `PE_OSCE_CONFLUENCE_PAGE_ID`; sin token.
Se pagina el listado y se validan ambos CSV antes de publicar una carpeta
`<data-dir>/raw/pe/osce_sanctions/api/snapshot-*`. Un fallo elimina la descarga
incompleta y usa CSV locales en las rutas existentes; si no hay archivos locales,
usa la última carpeta completa. Sin respaldo, la ejecución falla explícitamente.
En modo API, ambos CSV deben tener filas: se rechaza un adjunto vacío y solo se
usa un fallback con los dos CSV no vacíos. El modo file conserva su contrato.
El fallback se registra como advertencia; no demuestra que los datos estén frescos.
Las carpetas completas se conservan; su limpieza es una tarea manual de operación.
Los IDs y enlaces conservan la procedencia existente. MERGE no borra sanciones
ausentes de publicaciones posteriores. No cambia restricciones públicas.
Depende de #18, apilado sobre #17. Antes de cargar datos reales, completar el
[preflight de migración](osce_migration.md), verificar el respaldo y aprobar el alcance.

## Pruebas y ejecución

Desde `etl/`, con Docker disponible para la integración aislada:
```bash
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --frozen --extra dev
uv run pytest tests/test_pe_osce_sanctions_api.py tests/test_pe_osce_sanctions_pipeline.py
uv run pytest -o addopts='' -m integration tests/integration/test_pe_osce_sanctions_integration.py
PE_OSCE_SOURCE_MODE=api uv run bracc-etl run --source pe_osce_sanctions --data-dir /ruta/datos --neo4j-uri "$OSCE_TEST_URI" --neo4j-password "$OSCE_TEST_PASSWORD"
```
La integración usa Neo4j temporal y respuestas HTTP sintéticas, sin red externa.
Usar primero una base aislada; una ejecución del runner escribe en su destino.
Para una carga en la base existente, acordar el alcance y respaldarla antes.
Después, la UI Docker consulta los datos locales como siempre.

Rollback: volver a `PE_OSCE_SOURCE_MODE=file` o revertir el código. Esto no revierte
datos ya cargados; para ello restaurar el respaldo. Scheduler, SEACE OCDS y frescura
en frontend pertenecen a los siguientes bloques del plan de automatización.
