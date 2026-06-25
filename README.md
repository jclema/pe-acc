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

## Acceso demo

Para evitar depender del registro manual, el proyecto incluye un usuario demo fijo para el frontend:

- email: `demo@pe-acc.local`
- contraseña: `peacc-demo-2026`
- código de invitación para nuevos registros manuales: `demo`

Si el usuario demo no existe todavía en tu instancia local:

```bash
make ensure-demo-user
```

El bootstrap de Perú también lo crea automáticamente:

```bash
make bootstrap-pe-demo
```

## Pruebas manuales

La forma más rápida de validar el MVP hoy es usando casos reales ya cargados en el grafo.

### Caso 1. Proveedor con sanción visible

- `RUC`: `20100994128`
- `Proveedor`: `CONSTRUCTORA DOS DE MAYO S.A.`

Qué deberías poder probar en [http://localhost:3000](http://localhost:3000):

1. iniciar sesión con el usuario demo
2. buscar `20100994128`
3. abrir la ficha del proveedor
4. entrar al explorador del grafo
5. pasar el mouse sobre el nodo de sanción
6. hacer click en el nodo y en la arista

Qué deberías ver:

- nodo del proveedor y nodo de sanción conectados
- tooltip ampliado para la sanción
- `Tipo` en lenguaje más humano
- `Detalle` cuando exista motivo de sanción
- `Resolución`, `Vigencia` y `Fuente`
- detalle de arista con texto más claro, por ejemplo `Proveedor sancionado`

### Caso 2. Proveedor con sanción judicial

- `RUC`: `10040039711`
- `Proveedor`: `BARRETO MARCELO TEODORO`

Qué valida:

- cruce `Provider -> HAS_SANCTION -> Sanction`
- lectura de sanciones judiciales
- comportamiento del tooltip y panel de detalle en otro tipo de sanción

### Validación por Neo4j Browser

En [http://localhost:7474](http://localhost:7474):

- usuario: `neo4j`
- contraseña: `changeme`

Consulta útil:

```cypher
MATCH (p:Provider)-[:HAS_SANCTION]->(s:Sanction)
RETURN p.ruc, p.legal_name, s.sanction_id, s.type, s.sanction_source
LIMIT 10;
```

Conteo de relaciones:

```cypher
MATCH (:Provider)-[r:HAS_SANCTION]->(:Sanction)
RETURN count(r) AS total_relaciones;
```

### Validación por API

- [http://localhost:8000/health](http://localhost:8000/health)
- [http://localhost:8000/docs](http://localhost:8000/docs)

Ruta útil para inspección:

- `GET /api/v1/public/graph/proveedor/{ruc}`

### Si algo no se ve bien en la UI

- haz recarga fuerte del navegador
- confirma que el stack esté sano con `docker compose ps`
- revisa logs con `docker compose logs -f frontend` y `docker compose logs -f api`
- vuelve a probar primero el caso `20100994128`, que es hoy el caso demo principal

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

## Adopción selectiva desde `br-acc`

No buscamos copiar el upstream completo. La idea es portar solo lo que aumente valor real para Perú sin meter complejidad prematura.

### Fase 1. Utilidad cívica inmediata

- `landing orientada a búsqueda`
  Para que la home sirva como punto de entrada real a periodistas, OSC e investigadores.
- `source registry` visible
  Para mostrar qué fuentes peruanas existen, cuáles están cargadas y cuáles siguen parciales.
- `meta` más clara
  Para exponer salud del sistema, cobertura, fecha de corte y estado de fuentes.

Prerequisitos:

- `SUNAT + OSCE` ya funcionales
- estructura de [docs/source_registry_pe_v1.csv](/Users/juancamilo/Documents/pe-acc/docs/source_registry_pe_v1.csv) mantenida al día

### Fase 2. Operación y trazabilidad

- `progreso ETL` visible
  Para que quien contribuya pueda entender qué está cargando y qué se rompió.
- `observabilidad básica`
  Logs más claros, healthchecks mejores y estado del stack más transparente.
- `cache` cuando haga falta
  Útil cuando el proyecto se publique y necesitemos respuestas más rápidas en búsqueda y metadatos.

Prerequisitos:

- cargas reales más frecuentes
- mayor volumen de datos de `SUNAT` y `SEACE / CONOSCE`

### Fase 3. Analítica pública avanzada

- `reportes` o vistas demostrativas
  Casos concretos como proveedores sancionados, concentración en entidades o cruces contratación-presupuesto.
- `patrones investigativos`
  Solo cuando los joins principales sean confiables y explicables.

Prerequisitos:

- `Provider -> Process/Award -> Entity`
- primera integración útil de `MEF`
- criterio claro de trazabilidad y límites interpretativos

### Qué no es prioridad por ahora

- chatbot AI
- monitor OSINT amplio
- activity feeds complejos
- journeys o módulos de producto muy acoplados al upstream
- infraestructura completa del ecosistema `EGOS`

Regla práctica:

- adoptar primero lo que mejore `búsqueda`, `trazabilidad`, `cobertura visible` y `operación`
- diferir lo que requiera demasiada complejidad sin mejorar todavía el valor visible para Perú

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

Si vas a portar ideas desde el upstream:

1. explica qué problema resuelve en el contexto peruano
2. define si aporta a `Fase 1`, `Fase 2` o `Fase 3`
3. evita traer módulos completos si solo necesitamos una parte
4. prioriza piezas reutilizables sobre features acopladas al caso Brasil

## Próximos pasos

- cerrar pipeline real de `SEACE / CONOSCE`
- mejorar carga masiva a Neo4j para conjuntos grandes
- preparar despliegue público controlado
- incorporar contexto presupuestal del `MEF`

## Créditos

Este proyecto parte del trabajo original de [`br-acc`](https://github.com/enioxt/br-acc) y lo adapta al contexto peruano.

## Licencia

[GNU Affero General Public License v3.0](LICENSE)
