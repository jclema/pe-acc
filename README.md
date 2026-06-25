# PE-ACC

**Grafo abierto de integridad pública para Perú.**

PE-ACC es un fork de [`br-acc`](https://github.com/brunoclz/br-acc) orientado a Perú. Su objetivo es cruzar datos públicos de proveedores, sanciones, procesos de contratación y contexto presupuestal para apoyar vigilancia cívica, periodismo e investigación de interés público.

El foco actual no es “cubrir todo”, sino demostrar valor con un MVP funcional y trazable.

## Qué hace hoy

- Busca proveedores por `RUC`
- Muestra fichas de proveedor y relaciones en el grafo
- Carga identidad base desde `SUNAT`
- Enlaza sanciones desde `OSCE` y listados judiciales
- Expone API pública y frontend local para exploración

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

Estado de fuentes: [docs/source_registry_pe_v1.csv](/Users/juancamilo/Documents/pe-acc/docs/source_registry_pe_v1.csv)

## Quick Start

Levantar stack local:

```bash
cp .env.example .env
docker compose up -d
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

## Flujo recomendado del MVP

1. Cargar `SUNAT` para identidad de proveedores.
2. Cargar `OSCE` e inhabilitaciones judiciales.
3. Validar en UI relaciones `Provider -> HAS_SANCTION -> Sanction`.
4. Incorporar `SEACE / CONOSCE`.
5. Añadir `MEF` cuando el núcleo de contratación ya esté estable.

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

## Próximos pasos

- Cerrar pipeline real de `SEACE / CONOSCE`
- Mejorar carga masiva a Neo4j para conjuntos grandes
- Preparar despliegue público controlado
- Incorporar contexto presupuestal del `MEF`

## Créditos

Este proyecto parte del trabajo original de [`br-acc`](https://github.com/brunoclz/br-acc) y lo adapta al contexto peruano.

## Licencia

[GNU Affero General Public License v3.0](LICENSE)
