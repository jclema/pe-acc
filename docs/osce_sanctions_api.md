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
Cada snapshot nuevo incluye `manifest.json`: fecha UTC de descarga, página oficial,
URLs, tamaños y SHA-256. La descarga no acredita la fecha de corte de la fuente.
El runner registra modo (`api`, `fallback`, `file`), fecha y antigüedad en segundos;
para archivos anteriores sin manifiesto, la fecha y antigüedad son desconocidas.
`PE_OSCE_SNAPSHOT_KEEP=3` conserva los tres últimos snapshots administrados completos
(valor entero positivo). Solo elimina carpetas con ambos CSV, manifiesto y hashes
válidos; conserva archivos ajenos, snapshots antiguos sin manifiesto y carpetas
alteradas. Limpiar estas últimas requiere inspección manual. Un fallo de limpieza
emite advertencia y conserva la descarga válida.

La transformación y los IDs de sanciones son los existentes. Los enlaces usan
la procedencia de cada fila o la página registrada. La carga hace MERGE, no borra
sanciones ausentes de una publicación posterior. No cambia restricciones públicas.

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
datos ya cargados; para ello restaurar el respaldo. La programación debe activarse
únicamente sobre un destino aprobado después de la migración. SEACE OCDS y frescura en frontend pertenecen a otros bloques del plan.

## Operación programada

Ejemplo diario a las 02:00 en la zona horaria del servidor: instalar un wrapper
fuera del repositorio y un cron con el usuario operativo, después de aprobar el
destino. No activar este ejemplo contra producción sin migración y respaldo.
El archivo `/etc/peacc/osce.env` debe tener permisos 0600 y definir URI, usuario,
contraseña y directorio persistente; nunca versionarlo. Wrapper de ejemplo:
```bash
#!/usr/bin/env bash
set -euo pipefail
set -a
source /etc/peacc/osce.env
set +a
cd /ruta/pe-acc/etl
export PE_OSCE_SOURCE_MODE=api PE_OSCE_SNAPSHOT_KEEP=3
exec uv run --frozen bracc-etl run --source pe_osce_sanctions \
  --data-dir "$OSCE_DATA_DIR" --neo4j-uri "$OSCE_TEST_URI" \
  --neo4j-user "$OSCE_TEST_USER" --neo4j-password "$OSCE_TEST_PASSWORD"
```
Cron (crear previamente el directorio de logs y el de bloqueo con permisos adecuados):
```cron
0 2 * * * flock -n /ruta/locks/osce.lock /ruta/bin/run-osce >> /ruta/logs/osce.log 2>&1
```
Supervisar código de salida, fallbacks, antigüedad desconocida y fallos de retención;
rotar logs. Un fallback permite completar la carga pero no acredita actualización.
El operador debe decidir el umbral de antigüedad aceptable; no hay alertas automáticas.

Prueba reproducible con API oficial y Neo4j temporal (Docker; no toca otras bases):
```bash
PE_OSCE_LIVE_TEST=1 uv run --frozen pytest -o addopts='' -s \
  tests/integration/test_pe_osce_sanctions_integration.py::test_official_api_real_data_load_is_idempotent
```
Exige descarga efectiva, carga dos veces, verifica conteos y RUC de cada relación;
registra hashes y fecha de los archivos utilizados. Depende de la red y no corre
por defecto en CI. El entorno temporal no sustituye la migración del grafo existente.

Ensayo del 2026-10-02 (Neo4j temporal, API oficial): 9.882 filas leídas,
6.277 proveedores y 9.860 sanciones/relaciones tras dos cargas estables, sin RUC
cruzados. El normalizador existente descartó dos filas y consolidó 20 duplicados.
Los hashes y la fecha UTC se imprimen con la prueba y se guardan en el manifiesto;
los CSV reales no se versionan. Esta evidencia corresponde a esa publicación,
no acredita completitud histórica, vigencia legal ni fecha de corte oficial.
