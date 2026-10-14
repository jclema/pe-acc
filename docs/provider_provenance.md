# Procedencia de proveedores: SUNAT y OSCE

Primer bloque ETL del trabajo de procedencia multi-fuente. Ambas cargas conservan
observaciones normalizadas en `Provider.provider_source_records` (lista de JSON
canónico), fuentes en `sources` y atribución por campo en `provider_field_sources`
(JSON). Cada observación conserva RUC, valores, fuente, URL, archivo y corte cuando
el pipeline los proporciona; los metadatos ausentes quedan desconocidos.
Solo se copian campos explícitos de identidad/estado/geografía y procedencia;
no se archivan propiedades arbitrarias ni identificadores personales adicionales.

SUNAT tiene prioridad sobre OSCE para campos compartidos. Dentro de una fuente,
se prioriza el corte ISO más reciente; empates usan orden canónico determinista.
Valores vacíos no borran observaciones anteriores. Nombres `RUC <número>` no ocultan
nombres declarados. La procedencia escalar corresponde al nombre seleccionado;
para otros campos consultar su atribución, sin inferir que todos vienen de SUNAT.
Observaciones distintas se conservan; repetir una carga idéntica no agrega copias.
El historial no tiene poda automática: supervisar su tamaño antes de cargas masivas.
No se interpretan campos vacíos como retiradas o correcciones oficiales.

Al actualizar un proveedor legacy, se conserva una observación de los campos
conocidos existentes; sin fuente se etiqueta `legacy_unknown`. No se reconstruyen
fuentes ya sobrescritas en el pasado. Propiedades ajenas permanecen intactas.
Un historial inválido o de otro RUC aborta y revierte el lote; no se descarta.
Lectura y escritura comparten una transacción con bloqueo y reintentos del driver.
Se requiere la restricción **ya existente** `provider_ruc_unique` del esquema.
No instala restricciones, migra producción ni modifica relaciones de sanciones.
Otros importadores y operación real requieren bloques posteriores; API e interfaz
se describen abajo como entregas separadas de esta pila.

## Comprobación aislada

Desde el checkout del PR; Docker y uv disponibles:
```bash
cd etl
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/peacc-provider-provenance/etl-env"
export TMPDIR="$HOME/.cache/peacc-provider-provenance/tmp"
mkdir -p "$TMPDIR"
uv sync --frozen --extra dev
uv run --frozen pytest tests/test_provider_provenance.py -v
uv run --frozen pytest -o addopts='' tests/integration/test_provider_provenance.py -v \
  --basetemp="$HOME/.cache/peacc-provider-provenance/manual"
uv run --frozen pytest
uv run --frozen ruff check src tests
uv run --frozen mypy src
```
Las integraciones usan datos sintéticos y Neo4j temporal: ambos órdenes, dos cargas,
SUNAT por lotes, relaciones correctas, rollback del lote y concurrencia.
Rollback de código no revierte cargas; respaldar y verificar destino antes de operar.
Conservar la evidencia al volver al loader anterior requiere detener las cargas:
el loader anterior puede sobrescribir campos escalares, aunque deja estas propiedades.

## Contrato de lectura API

Las respuestas existentes de entidad y conexiones agregan `provider_provenance`
solo para `Provider` (otras entidades: `null`). Sus `fields` contienen únicamente
campos actuales de identidad, estado tributario y geografía del contrato ETL.
Cada campo tiene `source`, `source_url`, `source_dataset` y `extraction_date`,
con `null` para metadatos desconocidos. No se usa la fuente escalar para atribuir
los demás campos. `sources` conserva compatibilidad y usa la lista multi-fuente
cuando existe; no expresa atribución por campo.

`status` es `structured` para un objeto JSON de atribución, `legacy` cuando falta
y `invalid` cuando no puede leerse. Atribuciones de forma/fuente desconocida
quedan vacías. Demo/legacy no reconstruyen evidencia desde el historial.
Solo se aceptan enlaces HTTPS de dominios oficiales peruanos (`gob.pe` y sus
subdominios), sin credenciales ni puertos distintos de 443. El archivo se reduce
al nombre base; el corte requiere fecha ISO completa. No se deriva de la fecha
de descarga. El historial y el JSON interno nunca se aplanan en `properties`,
incluso en grafos. Los controles `PUBLIC_MODE` existentes siguen aplicándose.

Validación local de este bloque, sin conectarse a la base del usuario:
```bash
cd /home/edwar/.codex/worktrees/provider-provenance-api/pe-acc
(cd api && uv sync --frozen --extra dev)
make test-api
(cd api && uv run --frozen ruff check src tests && uv run --frozen mypy src)
make neutrality check-public-claims
```
Las pruebas usan entidades sintéticas y un driver simulado. No cambian esquema,
auth ni exposición de rutas; no acreditan una carga oficial. Integración prevista:
#20 (ETL) → draft API → draft interfaz. Otros importadores y operación real siguen
pendientes. Rollback de API: revertir este bloque; los campos ETL permanecen en
Neo4j y no requieren una migración.

## Lectura en la interfaz

La ficha principal y el detalle de proveedor ofrecen **Procedencia por campo**,
una sección nativa desplegable y operable con teclado. Muestra las fuentes
SUNAT/OSCE seleccionadas para cada campo, enlace oficial seguro y nombre de
archivo/corte informado. Cada metadato ausente muestra **Desconocido**.
En demo/legacy o atribución inválida no usa la fuente general ni la fecha de
descarga para completar campos. No repite el alias `name` si existe `legal_name`.

Desde el checkout de interfaz, sin servicios externos ni Neo4j:
```bash
cd /home/edwar/.codex/worktrees/provider-provenance-ui/pe-acc
(cd frontend && npm ci)
make test-frontend
(cd frontend && npm run lint && npm run type-check && npm run build)
make neutrality check-public-claims
python3 scripts/check_public_privacy.py --repo-root .
```
Verificación visual: componente real con fixture sintético, ancho 320 px, archivo
largo y teclado (Enter, Tab y Espacio). No valida un dataset oficial ni operación
real. Rollback de interfaz: revertir este bloque; los clientes anteriores pueden
ignorar el campo API opcional. Mantener orden #20 → API → interfaz.

## Enlaces en datos de demostración

Los CSV de `data/demo/pe/` usan entidades, resoluciones y URLs sintéticas como
`https://example.gob.pe/osce/001`. No existe una publicación oficial equivalente
que pueda inferirse de ese registro. La API omite esas URLs en la atribución
seleccionada; la interfaz reconoce los hosts de ejemplo conocidos y muestra
**Datos de demostración; sin enlace verificable.**, sin enlace clicable.
La ficha indica que incluye datos demo; conserva enlaces válidos de otros campos
cuando la evidencia es mixta. Aplica también a tarjetas de nodos y relaciones. Detectar un enlace demo
no atribuye campos legacy ni completa metadatos ausentes. Otros enlaces mantienen
sus validaciones; una URL admitida no acredita disponibilidad HTTP ni autenticidad
del registro. No se sustituyen URLs sintéticas por portales generales ni se carga
un dataset oficial para corregir la presentación. El volumen de datos no cambia.

Desde `/home/edwar/.codex/worktrees/demo-source-links/pe-acc`:
```bash
(cd api && uv sync --frozen --extra dev)
(cd frontend && npm ci)
make test-api test-frontend
(cd api && uv run --frozen ruff check src tests && uv run --frozen mypy src)
(cd frontend && npm run lint && npm run type-check && npm run build)
make neutrality check-public-claims
python3 scripts/check_public_privacy.py --repo-root .
```
Este fix se apila sobre el draft de interfaz #23. Rollback: revertir su commit;
no requiere migración ni cambios en ingesta, schema, auth o exposición de rutas.
