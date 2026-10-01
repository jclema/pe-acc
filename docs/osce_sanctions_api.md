# Sanciones OSCE: ingesta por API

Modo `api` basado en la referencia de `feat/data` (`7a98682`). Consulta la API
de adjuntos de [OSCE/OECE PNDA](https://osce-gob-pe.atlassian.net/wiki/pages/viewpage.action?pageId=106889269)
y descarga `sancionados.csv` e `inhabilitaciones_judiciales.csv`. Listado y descarga
comprobados el 2026-10-01. No incorpora multas ni otras fuentes del listado.

`PE_OSCE_SOURCE_MODE=file` sigue siendo el valor predeterminado; `api` activa
la descarga. `PE_OSCE_CONFLUENCE_BASE_URL` y `PE_OSCE_CONFLUENCE_PAGE_ID` permiten
configurar la ubicación. No necesita token. La disponibilidad depende del portal;
la fecha de descarga no se interpreta como fecha de corte y la licencia no se infiere.

Se pagina el listado y se validan ambos CSV antes de publicar una carpeta
`<data-dir>/raw/pe/osce_sanctions/api/snapshot-*`. Un fallo elimina la descarga
incompleta y usa CSV locales en las rutas existentes; si no hay archivos locales,
usa la última carpeta completa. Sin respaldo, la ejecución falla explícitamente.
El fallback se registra como advertencia; no demuestra que los datos estén frescos.
Las carpetas completas se conservan; su limpieza es una tarea manual de operación.

La transformación y los IDs de sanciones son los existentes. Los enlaces usan
la procedencia de cada fila o la página registrada. La carga hace MERGE, no borra
sanciones ausentes de una publicación posterior. No cambia restricciones públicas.

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
