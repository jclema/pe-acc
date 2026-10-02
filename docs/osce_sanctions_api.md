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
El fallback no acredita frescura. `manifest.json` registra fecha UTC, URL, tamaño
y SHA-256 de ambos CSV; fecha de descarga no equivale a corte oficial. Los logs
indican modo, fecha y antigüedad; sin manifiesto, la edad es desconocida.
Fallback y retención priorizan snapshots verificados por fecha UTC del manifiesto,
no por mtime. Legacy sin manifiesto quedan después, por mtime y con edad desconocida.
Manifiestos inválidos, archivos alterados y enlaces simbólicos se omiten y conservan.
`PE_OSCE_SNAPSHOT_KEEP=3` (entero positivo) conserva los últimos completos verificados;
fallos de limpieza advierten sin descartar la nueva descarga.
Las carpetas completas se conservan; su limpieza es una tarea manual de operación.
Los IDs y enlaces conservan la procedencia existente. MERGE no borra sanciones
ausentes de publicaciones posteriores. No cambia restricciones públicas.
Depende de #18, apilado sobre #17. Antes de cargar datos reales, completar el
[preflight de migración](osce_migration.md), verificar el respaldo y aprobar el alcance.

## Comprobación local

Desde la raíz del checkout, con uv y Docker; usa únicamente Neo4j temporal:
```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/peacc-pr6/etl-env"
export TMPDIR="$HOME/.cache/peacc-osce-operations/tmp"
mkdir -p "$TMPDIR"
cd etl
uv sync --frozen --extra dev
uv run --frozen pytest
uv run --frozen ruff check src tests
uv run --frozen mypy src
PE_OSCE_LIVE_TEST=1 uv run --frozen pytest -o addopts='' -s \
  --basetemp="$TMPDIR/osce-live" tests/integration/test_pe_osce_sanctions_integration.py
cd ..
make neutrality check-public-claims check-source-urls
gh pr checks 19 --repo jclema/pe-acc
```
La prueba live es opt-in: descarga efectiva, dos cargas, conteos/RUC estables y
manifiesto. Ensayo 2026-10-02: 9.882 filas, 6.277 proveedores y 9.860 sanciones y
relaciones, sin cruces; dos filas descartadas y 20 duplicados consolidados.
No acredita completitud histórica ni vigencia legal. No versionar CSV reales.

## Operación y rollback

Activar programación solo tras migración, respaldo y destino aprobados. Wrapper
externo 0600: cargar `/etc/peacc/osce.env` (credenciales y datos persistentes), entrar
al directorio `etl`, exportar `PE_OSCE_SOURCE_MODE=api PE_OSCE_SNAPSHOT_KEEP=3` y
usar `uv run --frozen bracc-etl run --source pe_osce_sanctions --data-dir "$OSCE_DATA_DIR"`
con `--neo4j-uri "$OSCE_TEST_URI" --neo4j-user "$OSCE_TEST_USER" --neo4j-password "$OSCE_TEST_PASSWORD"`.
Cron diario 02:00, zona del servidor; crear carpetas de bloqueo/logs antes:
```cron
0 2 * * * flock -n /ruta/locks/osce.lock /ruta/bin/run-osce >> /ruta/logs/osce.log 2>&1
```
Supervisar salida, fallbacks, edades y retención; rotar logs. Elegir umbral de edad;
no hay alertas automáticas. Un fallback exitoso no significa actualización. Rollback: detener cron, volver a modo file o revertir código; restaurar respaldo
para revertir el grafo. Los snapshots eliminados necesitan respaldo separado.
