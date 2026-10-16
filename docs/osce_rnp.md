# OSCE RNP: carga local

Fuente: [OSCE/OECE PNDA](https://osce-gob-pe.atlassian.net/wiki/spaces/PNDA/pages/106889267).
Listado y cabeceras comprobados el 2026-09-30. La fuente describe declaraciones
del último trámite aprobado del RNP, actualizadas mensualmente; no prueba control
actual ni responsabilidad legal. La licencia publicada no está especificada.
Estado: implementado y probado con datos sintéticos; `not_loaded` para datos reales.
La fecha de corte depende de los archivos entregados: no se infiere de la ejecución.

## Contrato

Colocar los tres archivos en `<data-dir>/raw/pe/osce_rnp/`, con nombres exactos:
`Socios.csv`, `representantes.csv`, `organos.csv`. ANSI/Windows-1252, separador `|`
o coma. Todos requieren `Tipo_Documento`, `Nro_Documento`, `Ruc_Proveedor` y nombre:
`Nombre_o_RazonSocial` en socios; `Nombre_RazonSocial` en los otros. Órganos exige `Cargo`.
Columnas faltantes/duplicadas o filas incompletas abortan antes de cargar vínculos.
Se omiten filas sin nombre, con documentos vacíos, extranjeros o no soportados.
Se recortan espacios; no se eliminan letras ni signos de documentos.

DNI: tipos `DOC. NACIONAL DE IDENTIDAD` y `DOC. NACIONAL DE IDENTIDAD/LE`, ocho
dígitos ASCII, incluidos ceros iniciales. RUC: tipo `REG. UNICO DE CONTRIBUYENTES`,
once dígitos con prefijo 10/15/17/20. Validación de formato, no de vigencia ni checksum.
El destino exige prefijo 20: esta fuente describe proveedores jurídicos.
Personas con DNI o RUC 10/15/17 usan `Person`, con claves separadas `dni`/`ruc`;
entidades con RUC 20 usan `Provider`. No se unen identidades por nombre.

Vínculos: `SOCIO_DE`, `REPRESENTA_A`, `MIEMBRO_ORGANO_DE`, dirigidos al proveedor.
Cada vínculo conserva nombre declarado, cargo, archivo, URL y SHA-256 del archivo.
Su clave incluye identidad de origen, destino, tipo, cargo y nombre normalizado.
Duplicados se fusionan; cargos/nombres distintos conservan declaraciones distintas.
Se preservan propiedades y vínculos previos; un placeholder puede recibir un nombre.
Personas siguen excluidas por las consultas públicas existentes.
La carga añade declaraciones: no elimina vínculos ausentes de un archivo posterior.

Los proveedores jurídicos de origen y destino añaden observaciones a `sources` y
`provider_source_records`, con archivo, URL y SHA-256. El nombre declarado pertenece
al origen; nunca se atribuye al proveedor destino ni se copian personas al historial
de `Provider`. La proyección de identidad prioriza SUNAT, sanciones OSCE, SEACE y
RNP; `provider_field_sources` identifica la evidencia seleccionada.
No se inventa una fecha de corte cuando el archivo no la informa. Repetir o invertir
el orden de carga conserva observaciones, identidad SUNAT y vínculos de sanciones.
Esto extiende la carga local; todavía no adquiere archivos del portal.

## Comprobar y ejecutar

Desde `etl/`, con Docker disponible para la prueba aislada:
```bash
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --frozen --extra dev
uv run pytest tests/test_pe_osce_rnp_pipeline.py -v -o cache_dir=/tmp/pe-rnp-review-cache
uv run pytest -o addopts='' -m integration tests/integration/test_pe_osce_rnp_integration.py -v
uv run bracc-etl run --source pe_osce_rnp --data-dir /ruta/datos --neo4j-uri "$RNP_TEST_URI" --neo4j-password "$RNP_TEST_PASSWORD" --neo4j-database neo4j
```
Usar primero una base aislada. Respaldar y verificar el destino antes de una carga real.
Inspección: `MATCH (a)-[r]->(p:Provider) WHERE r.source='osce_rnp' RETURN a,p,r;`.
Rollback: detener RNP y restaurar el backup previo en el destino; revertir código
no elimina datos. No borrar proveedores compartidos ni ejecutar bootstrap destructivo.
## Revisión en el explorador del grafo

El frontend permite filtrar «Socio de», «Representa a» y «Miembro de órgano
de administración de». Al seleccionar un vínculo RNP con procedencia, el detalle
muestra nombre y cargo declarados (si existen), archivo de origen, enlace a la
fuente y huella SHA-256 desplegable. No presenta un porcentaje de confianza ni
valor monetario para estas declaraciones. Los vínculos anteriores conservan
su detalle habitual.

La interfaz no carga los CSV ni cambia la consulta pública. Sin una carga RNP
previa, no aparecen vínculos nuevos. En modo público siguen excluidas las
personas; solo se muestran los vínculos corporativos que devuelve la API.
Varios vínculos entre los mismos nodos pueden superponerse en el dibujo:
desactiva los otros tipos de relación para inspeccionar cada declaración.

Para comprobar la interfaz:

```bash
cd frontend
npm ci
npm test
npm run build
npm run dev
```

Con la API y Neo4j locales disponibles, abre el grafo de un proveedor con RNP
cargado, alterna los tres filtros y selecciona un vínculo. Comprueba el cargo,
archivo, fuente y huella, y que la sanción y el nombre anteriores se conservan.
Para usar el proyecto completo: `docker compose up -d --build neo4j api frontend`
y abre `http://localhost:3000`. Después de que el grafo se estabilice, comprueba
zoom, desplazamiento, selección y filtros. El redibujado inactivo se pausa
automáticamente sin desactivar la navegación.

Un clic en un nodo fija su ficha ampliada para abrir la fuente sin mantener el cursor.
Ciérrala con su botón o con un clic en el fondo; ocultar el nodo también la cierra.

## Adquisición oficial acotada (adjuntos históricos)

Comprobación HTTP del 2026-10-15: la API oficial de metadatos de Confluence
[`child/attachment`](https://osce-gob-pe.atlassian.net/wiki/rest/api/content/106889267/child/attachment?limit=50&expand=version)
aún ofrece los tres adjuntos compatibles. Sus versiones informan publicación
`2021-11-11`; eso **no** es un corte comprobado ni prueba vigencia. La página
actualizada el 2026-10-01 destaca `conformacion_juridica.csv`, de otro esquema
(`FECHA_CORTE`, `TIPO_DOCUMENTO`, `NUMERO_DOCUMENTO`,
`NOMBRE_RAZONODENOMINACIONSOCIAL`, `RUC`, `TIPO_CONF_JURIDICA`, etc.). No se mapea
ese consolidado automáticamente ni se descarga para estas pruebas. Solo se
consultaron metadatos y cabeceras mediante rangos HTTP; sin conservar filas reales.

El conector separado usa la API de **metadatos/adjuntos** para descargar CSV;
no es una API de filas ni convierte una lectura local en API. Requiere reconocer
explícitamente el alcance histórico y no toca Neo4j:

```bash
cd etl
uv run python -m bracc_etl.rnp_acquisition --historical-three-files --output-dir /ruta/aislada/rnp
uv run pytest tests/test_rnp_acquisition.py -q
```

Publica un directorio `snapshot-*` solo después de validar los tres archivos,
Windows-1252, cabeceras/filas, registros válidos, tamaño completo y SHA-256.
Límite: 64 MiB por archivo y 96 MiB por conjunto; no admite adjuntos extra como
sustitutos. `manifest.json` conserva URLs, tamaño, huella, fecha de descarga y
fecha de versión si está disponible; licencia `unspecified` y corte `null`.
Una fecha de descarga o publicación no se convierte en fecha de observación.
Ante fallo, solo reutiliza un snapshot completo con manifiesto, huellas y CSV
válidos; nunca mezcla archivos de ejecuciones diferentes ni usa enlaces simbólicos.
No borra snapshots previos. El fallback se informa en el log.

Para comprobar compatibilidad, las pruebas pasan los tres archivos del snapshot
al transformador existente. El CLI de carga sigue usando el contrato local de
arriba; el conector no promueve snapshots a producción. Un operador debe revisar
corte, licencia y utilidad histórica antes de cualquier reprocesamiento. Queda
pendiente adaptar y validar el consolidado actual con su diccionario de tipos y
restricciones públicas. La disponibilidad de adjuntos históricos no cierra esa brecha.
