# Demo Data (Synthetic)

This directory is reserved for synthetic, public-safe demo data only.

Rules:
- No real CPF or personal identifiers.
- No `Person` / `Partner` labels.
- No operational metadata.

Use generator:

```bash
python3 scripts/generate_demo_dataset.py --output data/demo/synthetic_graph.json
```

## Peru MVP demo CSVs

The `data/demo/pe/` subtree contains small public-safe CSVs for the Peru MVP pipelines:

- `sunat_ruc/providers.csv`
- `osce_sanctions/sanctions.csv`
- `seace_conosce/processes.csv`

Copy them into the ETL input layout with:

```bash
make prepare-pe-demo-data
```

Then run the Peru ETL bundle with:

```bash
make etl-pe-demo
```
