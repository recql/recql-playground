"""Dispatcher: build logical demo catalog → load into a backend pack.

  python -m examples.generator.run --backend postgres --database postgres://…
  python -m examples.generator.run --backend oracle --database oracle://…
  python -m examples.generator.run --backend mariadb --database mariadb://…
  python -m examples.generator.run --backend mongodb --database mongodb://…
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def run(
    dsn: str,
    *,
    backend: str,
    encode_backend: str = "fake",
    dims: int = 8,
    max_movies: int | None = None,
    max_ratings: int | None = None,
) -> int:
    key = (backend or "").strip().lower()
    if key in ("oracle", "ora", "26ai"):
        from examples.generator.oracle.run import run as ora_run

        return await ora_run(
            dsn,
            encode_backend=encode_backend,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
    if key in ("mariadb", "maria", "mysql"):
        from examples.generator.mariadb.run import run as maria_run

        return await maria_run(
            dsn,
            encode_backend=encode_backend,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
    if key in ("mongodb", "mongo"):
        from examples.generator.mongodb.run import run as mongo_run

        return await mongo_run(
            dsn,
            encode_backend=encode_backend,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
    if key in ("postgres", "postgresql", "pg"):
        from examples.generator.postgres.run import run as pg_run

        return await pg_run(
            dsn,
            encode_backend=encode_backend,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
    if key in ("mssql", "sqlserver", "tsql"):
        from examples.generator.mssql.run import run as mssql_run

        return await mssql_run(
            dsn,
            encode_backend=encode_backend,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
    raise SystemExit(
        f"unknown backend {backend!r}; expected postgres|oracle|mariadb|mongodb|mssql"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RecQL demo catalog → database loader")
    p.add_argument("--database", required=True)
    p.add_argument(
        "--backend",
        required=True,
        help="Backend pack name (postgres|oracle|mariadb|mongodb); no default",
    )
    p.add_argument(
        "--encode-backend",
        default="fake",
        choices=("fake", "sentence_transformers", "auto"),
    )
    p.add_argument("--dims", type=int, default=8)
    p.add_argument("--max-movies", type=int, default=None)
    p.add_argument("--max-ratings", type=int, default=None)
    args = p.parse_args(argv)
    return asyncio.run(
        run(
            args.database,
            backend=args.backend,
            encode_backend=args.encode_backend,
            dims=args.dims,
            max_movies=args.max_movies,
            max_ratings=args.max_ratings,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
