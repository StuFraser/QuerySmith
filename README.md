# QuerySmith

Tiered execution-plan analysis agent. V1 targets SQL Server; see `design-notes/` for
scope and the intermediate representation (IR) schema.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . -r requirements-dev.txt
```

## Run tests

```bash
pytest -v
```
