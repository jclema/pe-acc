# Public Endpoint Matrix

## Public-safe defaults

- `PUBLIC_MODE=true`
- `PUBLIC_ALLOW_PERSON=false`
- `PUBLIC_ALLOW_ENTITY_LOOKUP=false`
- `PUBLIC_ALLOW_INVESTIGATIONS=false`
- `PATTERNS_ENABLED=false`

## Endpoint behavior

| Endpoint | Behavior with public-safe defaults |
|---|---|
| `GET /api/v1/entity/{cpf_or_cnpj}` | `403` (`Entity lookup endpoint disabled in public mode`) |
| `GET /api/v1/entity/by-element-id/{id}` | `403` (`Entity lookup endpoint disabled in public mode`) |
| `GET /api/v1/entity/{id}/connections` | Person/Partner targets filtered out |
| `GET /api/v1/search` | Person/Partner results filtered out |
| `GET /api/v1/graph/{entity_id}` | Person/Partner center blocked, person nodes filtered |
| `GET /api/v1/patterns/{entity_id}` | `404` (router not registered in PE-ACC) |
| `GET /api/v1/investigations/*` | `404` (router not registered in PE-ACC) |
| `GET /api/v1/public/meta` | Allowed |
| `GET /api/v1/public/patterns/company/{cnpj_or_id}` | `503` while pattern engine is disabled |
| `GET /api/v1/public/graph/company/{cnpj_or_id}` | Allowed |

## Exposure tiers

- `public_safe`: company/contract/sanction/aggregate entities allowed in public surface.
- `restricted`: person-adjacent entities, filtered by default.

## Retained upstream routers

The baseline, emendas, investigations, and general patterns routers remain in
source but are not registered in the PE-ACC app, in either public or private
mode. Their unit tests use an isolated app; this does not expose those routes in
production. The public patterns route listed above remains registered and gated.
