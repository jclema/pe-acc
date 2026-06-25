# PE-ACC

**Grafo abierto de integridad pública para Perú.**

PE-ACC es un fork de [`br-acc`](https://github.com/enioxt/br-acc) orientado a Perú. Su objetivo es cruzar datos públicos de proveedores, sanciones, procesos de contratación y contexto presupuestal para apoyar vigilancia cívica, periodismo e investigación de interés público.

El foco actual no es “cubrir todo”, sino demostrar valor con un MVP funcional y trazable.

## Qué hace hoy

- Busca proveedores por `RUC`
- Muestra fichas de proveedor y relaciones en el grafo
- Carga identidad base desde `SUNAT`
- Enlaza sanciones desde `OSCE` y listados judiciales
- Expone API pública y frontend local para exploración

## Demo actual

Hoy el prototipo ya permite revisar un subconjunto real del grafo peruano:

- `SUNAT / RUC`: carga parcial para identidad de proveedores
- `OSCE + inhabilitaciones judiciales`: cargadas y enlazadas al grafo
- `HAS_SANCTION`: `9,137` relaciones verificadas en Neo4j
- frontend local operativo en `http://localhost:3000`

Ejemplo validado en la UI:

- `CONSTRUCTORA DOS DE MAYO S.A.` por `RUC 20100994128`

Estado de fuentes: [docs/source_registry_pe_v1.csv](/Users/juancamilo/Documents/pe-acc/docs/source_registry_pe_v1.csv)

## En qué se diferencia del upstream

- Reorienta el dominio de Brasil a Perú
- Introduce pipelines `pe_*` para fuentes peruanas
- Simplifica la superficie del producto al núcleo MVP
- Prioriza datos reales y validación rápida antes que cobertura total

## Fuentes priorizadas

- `SUNAT / Padrón RUC`
- `OSCE / sanciones del Tribunal`
- `inhabilitaciones judiciales`
- `SEACE / CONOSCE`
- `MEF` como capa posterior de contexto presupuestal

## Quick Start

Levantar stack local:

```bash
cp .env.example .env
docker compose up -d
```

Ver estado del stack:

```bash
docker compose ps
```

Levantar demo Perú con ETL:

```bash
cp .env.example .env
bash scripts/bootstrap_pe_demo.sh
```

URLs locales:

- Frontend: [http://localhost:3000](http://localhost:3000)
- API health: [http://localhost:8000/health](http://localhost:8000/health)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Neo4j Browser: [http://localhost:7474](http://localhost:7474)

## Datos reales en este repo

El proyecto ya incluye la estructura para trabajar con fuentes peruanas:

- [data/raw/pe](/Users/juancamilo/Documents/pe-acc/data/raw/pe)
- [data/normalized/pe](/Users/juancamilo/Documents/pe-acc/data/normalized/pe)
- [etl/src/bracc_etl/pipelines/pe_sunat_ruc.py](/Users/juancamilo/Documents/pe-acc/etl/src/bracc_etl/pipelines/pe_sunat_ruc.py)
- [etl/src/bracc_etl/pipelines/pe_osce_sanctions.py](/Users/juancamilo/Documents/pe-acc/etl/src/bracc_etl/pipelines/pe_osce_sanctions.py)
- [etl/src/bracc_etl/pipelines/pe_seace_conosce.py](/Users/juancamilo/Documents/pe-acc/etl/src/bracc_etl/pipelines/pe_seace_conosce.py)

## Operación local

- El stack activo de desarrollo usa [docker-compose.yml](/Users/juancamilo/Documents/pe-acc/docker-compose.yml) en la raíz del repo.
- [infra/docker-compose.yml](/Users/juancamilo/Documents/pe-acc/infra/docker-compose.yml) existe como variante de infraestructura, pero el flujo normal local usa el compose de raíz.
- Los puertos del stack local quedaron ligados a `127.0.0.1` para reducir exposición accidental:
  - `127.0.0.1:3000` frontend
  - `127.0.0.1:8000` API
  - `127.0.0.1:7474` Neo4j Browser
  - `127.0.0.1:7687` Neo4j Bolt
- `api`, `frontend` y `neo4j` usan `healthchecks` y `restart: unless-stopped`.
- La API ahora reintenta la conexión a Neo4j en el arranque, lo que vuelve más estable el flujo `docker compose up -d`.

Comandos útiles:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f neo4j
```

## Flujo recomendado del MVP

1. Cargar `SUNAT` para identidad de proveedores.
2. Cargar `OSCE` e inhabilitaciones judiciales.
3. Validar en UI relaciones `Provider -> HAS_SANCTION -> Sanction`.
4. Incorporar `SEACE / CONOSCE`.
5. Añadir `MEF` cuando el núcleo de contratación ya esté estable.

## Roadmap

### Now

- consolidar `SUNAT + OSCE` como base real del grafo
- terminar ingestión útil de `SEACE / CONOSCE`
- mejorar la experiencia de búsqueda y ficha de proveedor

### Next

- cruzar `Provider -> Process/Award -> Entity`
- incorporar contexto presupuestal del `MEF`
- optimizar cargas grandes a Neo4j

### Later

- despliegue público estable
- capa de conflictos de interés y declaraciones
- mayor cobertura y actualización automatizada de fuentes

## Estado actual

- `pe_sunat_ruc`: implementado
- `pe_osce_sanctions`: implementado
- `pe_seace_conosce`: base inicial creada
- frontend traducido y rebrandeado a `PE-ACC`
- `origin` público: [https://github.com/jclema/pe-acc](https://github.com/jclema/pe-acc)

## API MVP

- `GET /health`
- `GET /api/v1/public/meta`
- `GET /api/v1/search`
- `GET /api/v1/public/graph/proveedor/{ruc}`

## Seguridad y alcance

PE-ACC muestra conexiones y trazabilidad de fuentes públicas. No produce scores de corrupción, no formula acusaciones y no debe interpretarse como prueba concluyente por sí mismo.

## Desarrollo

Mapa del repo:

```text
api/        FastAPI
etl/        pipelines y utilidades de ingestión
frontend/   React + Vite
infra/      Docker, Neo4j, bootstrap
scripts/    automatización local
docs/       documentación y registro de fuentes
data/       datos raw, normalizados y demo
```

## Cómo aportar

Hay varias formas de contribuir sin meterse de frente a toda la arquitectura:

- `Datos`: agregar muestras reales o documentadas de `SEACE / CONOSCE`, `MEF` u otras fuentes públicas peruanas.
- `ETL`: mejorar normalización, joins por `RUC` y rendimiento de carga hacia Neo4j.
- `Frontend`: pulir búsqueda, ficha de proveedor, trazabilidad visible y branding Perú.
- `API`: ampliar endpoints públicos para consultas cívicas útiles sin exponer datos sensibles.
- `Documentación`: registrar cobertura, huecos, licencias y limitaciones por fuente en [docs/source_registry_pe_v1.csv](/Users/juancamilo/Documents/pe-acc/docs/source_registry_pe_v1.csv).

Antes de abrir cambios grandes, conviene mantener este criterio:

- priorizar valor visible para Perú
- no bloquear el MVP por complejidad interna
- mantener trazabilidad clara por fuente
- evitar conclusiones acusatorias o rankings

Si vas a trabajar con datos nuevos:

1. deja el archivo original en `data/raw/pe/...`
2. documenta la fuente y fecha de corte
3. normaliza hacia `data/normalized/pe/...`
4. valida que el join principal quede visible en Neo4j o en la UI

## Próximos pasos

- cerrar pipeline real de `SEACE / CONOSCE`
- mejorar carga masiva a Neo4j para conjuntos grandes
- preparar despliegue público controlado
- incorporar contexto presupuestal del `MEF`

## Créditos

Este proyecto parte del trabajo original de [`br-acc`](https://github.com/enioxt/br-acc) y lo adapta al contexto peruano.

## Licencia

[GNU Affero General Public License v3.0](LICENSE)
