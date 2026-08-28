# recql-playground

Standalone demo / seed app for RecQL. Not required to use the library or CLI for queries.

## Install

```bash
pip install "recql @ git+https://github.com/recql/recql-python-core.git"
pip install "recql-cli @ git+https://github.com/recql/recql-python-cli.git"
pip install "recql-postgres @ git+https://github.com/recql/recql-python-postgres.git"  # or mariadb / oracle
pip install "recql-playground @ git+https://github.com/recql/recql-playground.git"
```

## Seed

```bash
recql-seed --database postgres://... --backend postgres
# or
recql --seed --database postgres://... --backend postgres
```

## Layout

- `examples/` — hybrid / boosted / generator demos
- `docker/` — compose helpers
