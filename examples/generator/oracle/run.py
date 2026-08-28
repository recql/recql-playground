"""Run: build logical catalog → load into Oracle 26ai."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from recql_oracle.connect import parse_oracle_dsn

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def run(
    dsn: str,
    *,
    encode_backend: str = "fake",
    dims: int = 8,
    max_movies: int | None = None,
    max_ratings: int | None = None,
) -> int:
    import oracledb

    from examples.generator.catalog import build_demo_catalog
    from examples.generator.oracle.load import load_catalog

    catalog = build_demo_catalog(
        dims=dims,
        encode_backend=encode_backend,
        max_movies=max_movies,
        max_ratings=max_ratings,
    )
    user, password, easy = parse_oracle_dsn(dsn)
    conn = await oracledb.connect_async(user=user, password=password, dsn=easy)
    try:
        summary = await load_catalog(
            conn,
            catalog,
            engine_config={"example": "generator", "encode_backend": encode_backend},
        )
    finally:
        await conn.close()
    print(f"loaded oracle {summary} movielens={catalog.meta.get('movielens')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Load RecQL demo catalog into Oracle 26ai")
    p.add_argument("--database", required=True, help="oracle://user:pass@host:1521/FREEPDB1")
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
            encode_backend=args.encode_backend,
            dims=args.dims,
            max_movies=args.max_movies,
            max_ratings=args.max_ratings,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
