"""Run: build logical catalog → load into MongoDB."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

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
    from examples.generator.catalog import build_demo_catalog
    from examples.generator.mongodb.load import load_catalog
    from recql_mongodb.db import create_client

    catalog = build_demo_catalog(
        dims=dims,
        encode_backend=encode_backend,
        max_movies=max_movies,
        max_ratings=max_ratings,
    )
    client, db = await create_client(dsn)
    try:
        summary = await load_catalog(
            db,
            catalog,
            engine_config={"example": "generator", "encode_backend": encode_backend},
        )
    finally:
        client.close()
    print(f"loaded mongodb {summary} movielens={catalog.meta.get('movielens')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Load RecQL demo catalog into MongoDB")
    p.add_argument("--database", required=True, help="mongodb://host:27017/recql")
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
