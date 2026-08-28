"""Offline demo data: MovieLens → logical catalog → load per database.

| Path | Role |
|---|---|
| `movielens.py` | Download/cache GroupLens **ml-100k** |
| `catalog.py` | Map movies/users/ratings → items / users / interactions / ALS + LightGBM |
| `postgres/` | Postgres DDL + `load.py` + `engine.yaml` |
| `oracle/` | Oracle 26ai DDL + `load.py` + `engine.yaml` |
| `mariadb/` | MariaDB 11.7+ VECTOR/FULLTEXT DDL + `load.py` + `engine.yaml` |
| `run.py` | Dispatcher (`--backend postgres\|oracle\|mariadb\|mongodb`) |

**Limits:** full set by default (Docker). Cap with `--max-movies` / `--max-ratings`
or `RECQL_MOVIELENS_MAX_MOVIES` / `RECQL_MOVIELENS_MAX_RATINGS`. Cache dir:
`~/.cache/recql/movielens` (override `RECQL_MOVIELENS_CACHE`).

See repo root `README.md` and `examples/README.md` for Compose + DSNs.
"""
