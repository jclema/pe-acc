# SEACE/CONOSCE: contrato local y procedencia

El pipeline `pe_seace_conosce` sigue siendo un scaffold de carga local de
`<data-dir>/pe/seace_conosce/processes.csv` (o `seace_conosce/processes.csv`).
No adquiere datos por HTTP ni convierte las publicaciones oficiales. Las columnas
normalizadas se ilustran exclusivamente con la fixture sintética
`etl/tests/fixtures/pe_seace_conosce_processes.csv`; no son un esquema oficial.
Estado real: `scaffolded` / `not_loaded`.

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
real; el scaffold no los infiere ni garantiza vigencia. Sin cambios de API/UI ni
política pública. Antes de reprocesar datos reales, un operador debe respaldar y
validar el destino. Para rollback posterior, restaurar el backup; revertir código
no revierte datos ni autoriza borrar proveedores compartidos.
