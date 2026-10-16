# SEACE/CONOSCE: contrato local y procedencia

El pipeline `pe_seace_conosce` conserva la carga local de
`<data-dir>/pe/seace_conosce/processes.csv` (o `seace_conosce/processes.csv`).
La adquisición HTTP es separada; el adaptador oficial se describe abajo. Las columnas
normalizadas se ilustran exclusivamente con la fixture sintética
`etl/tests/fixtures/pe_seace_conosce_processes.csv`; no son un esquema oficial.
Estado: implementado para adjudicaciones corporativas de ganador único; producción `not_loaded`.

Cada observación del proveedor conserva nombre declarado, URL, fecha informada,
archivo `processes.csv` y SHA-256 cuando se usa `extract`. Dos adjudicaciones del
mismo RUC con enlaces diferentes conservan ambas evidencias. La proyección de
identidad usa el merge transaccional compartido: SUNAT > sanciones OSCE > SEACE >
RNP. Campos vacíos no borran valores conocidos. `provider_field_sources` atribuye
la selección; `provider_source_records` conserva las observaciones diferentes.
Las fechas del CSV no se sustituyen por la fecha de ejecución.

Los identificadores y vínculos `PUBLISHED`, `HAS_AWARD`, `WINNER` se mantienen.
Las pruebas con Neo4j temporal verifican ambos órdenes con SUNAT/OSCE, repetición,
identidad, las dos observaciones de un RUC y sus adjudicaciones y sanciones:

```bash
cd etl
uv run pytest tests/test_pe_seace_conosce_pipeline.py -q
uv run pytest -q -o addopts='' -m integration tests/integration/test_pe_seace_provenance.py
uv run ruff check src/ tests/
uv run mypy src/
```

Las publicaciones pueden estar incompletas o tener revisiones. Una adjudicación
no demuestra firma de contrato, pago, control actual ni responsabilidad legal.
Licencia y corte del archivo normalizado deben documentarse al preparar una carga
real; el cargador no los infiere ni garantiza vigencia. Antes de reprocesar datos
reales, un operador debe respaldar y
validar el destino. Para rollback posterior, restaurar el backup; revertir código
no revierte datos ni autoriza borrar proveedores compartidos.

## Adquisición oficial de adjudicaciones por año

Verificado por HTTP el 2026-10-15: el [portal oficial](https://bi.seace.gob.pe/pentaho/api/repos/%3Apublic%3Aportal%3Adatosabiertos.html/content?userid=public&password=key)
genera enlaces a XLSX mediante su
[script publicado](https://bi.seace.gob.pe/pentaho/plugin/pentaho-cdf-dd/api/resources/public/portal/js/renderhtmlv2.js?userid=public&password=key).
El [XLSX 2026 de adjudicaciones](https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/adjudicaciones/2026/CONOSCE_ADJUDICACIONES2026_0.xlsx)
respondió a HEAD (9 359 469 bytes; Last-Modified 2026-10-09). Rangos HTTP acotados
permitieron comprobar la estructura ZIP, la referencia a `Sheet1` y sus 25 columnas
sin descargar ni conservar filas reales. El [diccionario oficial](https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/Diccionario.xlsx)
describe los campos; el archivo usa `RUC PROVEEDOR` con espacio, aunque el
diccionario lo representa como `RUC_PROVEEDOR`.

El conector separado descarga **un XLSX anual de adjudicaciones**, con año explícito
entre 2018 y el actual. Es descarga de archivo oficial, no API de filas. La ruta
Pentaho que contiene `/api/` entrega HTML; no acredita una REST de contrataciones.
No se enumeran ni descargan todos los años ni otros datasets:

```bash
cd etl
uv run python -m bracc_etl.seace_acquisition --year 2026 --output-dir /ruta/aislada/seace
uv run pytest tests/test_seace_acquisition.py -q
```

Límite de descarga: 32 MiB. Solo publica `snapshot-*` con XLSX y `manifest.json`
tras comprobar longitud, ZIP/CRC, límites del contenido descomprimido, XML seguro,
paquete/referencia de hoja, las 25 columnas observadas y filas no vacías. Cambios de
esquema abortan; no se renombran columnas ni se adivinan contratos. El manifiesto
conserva URL, año, bytes, SHA-256, descarga y Last-Modified; licencia `unspecified` y
corte `null`. Año de convocatoria y fecha del servidor no prueban corte completo.
`valid_snapshot` comprueba integridad local; no acredita autenticidad ni vigencia.
Los fallos dejan snapshots previos intactos y no seleccionan fallback automáticamente.

**El descargador no produce `processes.csv` ni carga Neo4j.** El diccionario
incluye personas naturales y códigos 99 para proveedores extranjeros; no deben
pasarse sin revisión a flujos públicos. La adquisición no amplía exposición pública
ni modifica reglas de personas.
La descarga no cambia el estado de carga. Un operador debe controlar acceso,
retención, licencia y corte de los archivos antes de cualquier carga. Para rollback
del conector basta revertir código; los archivos adquiridos permanecen en el destino.

## Del snapshot oficial al grafo

Copiar el contenido completo del snapshot validado a
`<data-dir>/pe/seace_conosce/official/` (XLSX y manifiesto). Ese directorio tiene
prioridad sobre el CSV normalizado; si es inválido, aborta sin fallback al CSV.
El adaptador verifica la huella y lee celdas por dirección, conservando vacíos y
ceros iniciales. Agrupa todo el archivo por convocatoria e ítem antes de aplicar
`--limit`. Solo carga personas jurídicas con RUC 20 y un ganador único por ítem;
excluye prorrata, personas naturales, consorcios y proveedores extranjeros. Filas
contradictorias de un mismo ganador abortan antes de cargar. No se infieren cuotas.

Las claves de adjudicación incluyen convocatoria, ítem y RUC; las de proceso usan
el código de convocatoria. Los montos vienen de `MONTO_ADJUDICADO_ITEM_SOLES`:
`currency=PEN`, aunque MONEDA describa otra moneda original del procedimiento.
El estado del ítem se guarda en la adjudicación, no se atribuye al proceso entero.
Archivo, SHA-256, fila y URL se conservan; el fragmento `#row=N` identifica la fila
del XLSX descargable, no es un enlace a un expediente individual. `extraction_date`
es la descarga del manifiesto; el corte oficial permanece desconocido.

```bash
uv run bracc-etl run --source pe_seace_conosce --data-dir /ruta/datos --limit 20 --neo4j-uri "$SEACE_TEST_URI" --neo4j-password "$SEACE_TEST_PASSWORD"
```

En el explorador, usar profundidad 3 para seguir entidad → proceso → adjudicación
→ proveedor. Fijar la adjudicación con un clic muestra fecha, monto, archivo, fila,
enlace y huella; el vínculo RNP muestra corte y vigencia declarados. Las pruebas en
base aislada no acreditan cobertura completa ni carga productiva. El rollback de
una carga sigue requiriendo restaurar el respaldo previo.
