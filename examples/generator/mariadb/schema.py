"""Demo MariaDB DDL — VECTOR + FULLTEXT (MariaDB 11.7+)."""

from __future__ import annotations


async def apply_demo_schema(conn, *, text_dims: int = 8, als_dims: int | None = None) -> None:
    """``conn`` is an aiomysql connection."""
    td = int(text_dims)
    ad = int(als_dims if als_dims is not None else td)

    stmts = [
        """
        CREATE TABLE IF NOT EXISTS items (
          item_id VARCHAR(128) PRIMARY KEY,
          attrs JSON NOT NULL,
          created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          derived_popular_rank DOUBLE,
          search_text TEXT NOT NULL,
          FULLTEXT INDEX items_search_ft (search_text)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
          user_id VARCHAR(128) PRIMARY KEY,
          attrs JSON NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS interactions (
          user_id VARCHAR(128) NOT NULL,
          item_id VARCHAR(128) NOT NULL,
          label DOUBLE,
          created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (user_id, item_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS models (
          name VARCHAR(128) NOT NULL,
          policy_type VARCHAR(64),
          version VARCHAR(64) NOT NULL DEFAULT 'v1',
          feature_spec JSON,
          `blob` LONGBLOB,
          created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (name, version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pagination_seen (
          page_key VARCHAR(512) NOT NULL,
          item_id VARCHAR(128) NOT NULL,
          expires_at DATETIME(6) NOT NULL,
          PRIMARY KEY (page_key, item_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS artifact_registry (
          kind VARCHAR(32) NOT NULL,
          name VARCHAR(128) NOT NULL,
          version VARCHAR(64) NOT NULL,
          dims INT,
          config_hash VARCHAR(64),
          feature_spec JSON,
          created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
          PRIMARY KEY (kind, name, version)
        )
        """,
        "CREATE INDEX IF NOT EXISTS items_popular_idx ON items (derived_popular_rank)",
        "CREATE INDEX IF NOT EXISTS items_created_idx ON items (created_at DESC)",
    ]
    async with conn.cursor() as cur:
        for sql in stmts:
            await cur.execute(sql)
        for sql in (
            """
            ALTER TABLE items
              MODIFY created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            """,
            """
            ALTER TABLE interactions
              MODIFY created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            """,
            """
            ALTER TABLE pagination_seen
              MODIFY expires_at DATETIME(6) NOT NULL
            """,
        ):
            try:
                await cur.execute(sql)
            except Exception:
                pass
        await conn.commit()

    await _ensure_embedding_tables(conn, text_dims=td, als_dims=ad)


async def _ensure_embedding_tables(conn, *, text_dims: int, als_dims: int) -> None:
    """Recreate embedding tables when dims change (VECTOR width is fixed at CREATE)."""
    td, ad = int(text_dims), int(als_dims)
    async with conn.cursor() as cur:
        await cur.execute("DROP TABLE IF EXISTS text_embeddings")
        await cur.execute("DROP TABLE IF EXISTS als_user_embeddings")
        await cur.execute("DROP TABLE IF EXISTS als_item_embeddings")
        await cur.execute("DROP TABLE IF EXISTS als_embeddings")
        await cur.execute(
            f"""
            CREATE TABLE text_embeddings (
              embedding_name VARCHAR(128) NOT NULL,
              entity_id VARCHAR(128) NOT NULL,
              embedding VECTOR({td}) NOT NULL,
              PRIMARY KEY (embedding_name, entity_id),
              VECTOR INDEX text_embeddings_vec (embedding) M=6 DISTANCE=cosine
            )
            """
        )
        await cur.execute(
            f"""
            CREATE TABLE als_user_embeddings (
              user_id VARCHAR(128) PRIMARY KEY,
              embedding VECTOR({ad}) NOT NULL,
              VECTOR INDEX als_user_embeddings_vec (embedding) M=6 DISTANCE=cosine
            )
            """
        )
        await cur.execute(
            f"""
            CREATE TABLE als_item_embeddings (
              item_id VARCHAR(128) PRIMARY KEY,
              embedding VECTOR({ad}) NOT NULL,
              VECTOR INDEX als_item_embeddings_vec (embedding) M=6 DISTANCE=cosine
            )
            """
        )
        await conn.commit()
