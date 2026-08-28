"""Demo Microsoft SQL Server 2025 DDL — Vector (VECTOR(dims)) + Full-Text Search."""

from __future__ import annotations

import asyncio
from typing import Any

from recql_mssql.db import MssqlDb, execute, fetch_one


async def apply_demo_schema(db: Any, *, text_dims: int = 8, als_dims: int | None = None) -> None:
    """Create demo tables, vector columns, and full-text index for the MovieLens demo stack."""
    d = db if isinstance(db, MssqlDb) else MssqlDb(db)
    td = int(text_dims)
    ad = int(als_dims if als_dims is not None else td)

    ddls = [
        """
        IF OBJECT_ID('items', 'U') IS NULL
        CREATE TABLE items (
            item_id VARCHAR(64) NOT NULL CONSTRAINT pk_items PRIMARY KEY,
            title NVARCHAR(256) NULL,
            search_text NVARCHAR(MAX) NULL,
            derived_popular_rank INT NULL,
            created_at DATETIME2 NULL,
            attrs NVARCHAR(MAX) NULL
        );
        """,
        """
        IF OBJECT_ID('users', 'U') IS NULL
        CREATE TABLE users (
            user_id VARCHAR(64) NOT NULL CONSTRAINT pk_users PRIMARY KEY,
            attrs NVARCHAR(MAX) NULL
        );
        """,
        """
        IF OBJECT_ID('interactions', 'U') IS NULL
        CREATE TABLE interactions (
            user_id VARCHAR(64) NOT NULL,
            item_id VARCHAR(64) NOT NULL,
            label FLOAT NULL,
            created_at DATETIME2 NULL,
            CONSTRAINT pk_interactions PRIMARY KEY (user_id, item_id)
        );
        """,
        """
        IF OBJECT_ID('models', 'U') IS NULL
        CREATE TABLE models (
            name VARCHAR(128) NOT NULL,
            version VARCHAR(64) NOT NULL,
            policy_type VARCHAR(64) NULL,
            feature_spec NVARCHAR(MAX) NULL,
            blob_data VARBINARY(MAX) NULL,
            created_at DATETIME2 NULL,
            CONSTRAINT pk_models PRIMARY KEY (name, version)
        );
        """,
    ]
    for ddl in ddls:
        await execute(d, ddl)

    await _ensure_embedding_tables(d, text_dims=td, als_dims=ad)

    # Full-text catalog and index setup on items(search_text) if FTS is installed
    try:
        row = await fetch_one(d, "SELECT FULLTEXTSERVICEPROPERTY('IsFullTextInstalled') AS is_fts")
        if row and int(row.get("is_fts") or 0) == 1:
            await execute(
                d,
                """
                IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'recql_ft_cat')
                    CREATE FULLTEXT CATALOG recql_ft_cat AS DEFAULT;
                """
            )
            await execute(
                d,
                """
                IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('items'))
                    CREATE FULLTEXT INDEX ON items(search_text) KEY INDEX pk_items ON recql_ft_cat WITH CHANGE_TRACKING AUTO;
                """
            )
    except Exception:
        pass


async def _ensure_embedding_tables(db: MssqlDb, *, text_dims: int, als_dims: int) -> None:
    """Ensure embedding tables with requested vector dimensions."""
    td, ad = int(text_dims), int(als_dims)
    for table in ("text_embeddings", "als_user_embeddings", "als_item_embeddings"):
        # If table exists with different vector width, it would need recreate or create if not exists
        pass

    await execute(
        db,
        f"""
        IF OBJECT_ID('text_embeddings', 'U') IS NULL
        CREATE TABLE text_embeddings (
            embedding_name VARCHAR(64) NOT NULL,
            entity_id VARCHAR(64) NOT NULL,
            embedding VECTOR({td}) NOT NULL,
            CONSTRAINT pk_text_embeddings PRIMARY KEY (embedding_name, entity_id)
        );
        """
    )
    await execute(
        db,
        f"""
        IF OBJECT_ID('als_user_embeddings', 'U') IS NULL
        CREATE TABLE als_user_embeddings (
            user_id VARCHAR(64) NOT NULL CONSTRAINT pk_als_user PRIMARY KEY,
            embedding VECTOR({ad}) NOT NULL
        );
        """
    )
    await execute(
        db,
        f"""
        IF OBJECT_ID('als_item_embeddings', 'U') IS NULL
        CREATE TABLE als_item_embeddings (
            item_id VARCHAR(64) NOT NULL CONSTRAINT pk_als_item PRIMARY KEY,
            embedding VECTOR({ad}) NOT NULL
        );
        """
    )


async def wait_fts_populated(db: Any, *, timeout_s: float = 10.0) -> None:
    """Wait for full-text index crawl to complete if fulltext is active."""
    d = db if isinstance(db, MssqlDb) else MssqlDb(db)
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            row = await fetch_one(
                d,
                """
                SELECT FULLTEXTCATALOGPROPERTY('recql_ft_cat', 'PopulateStatus') AS status,
                       FULLTEXTCATALOGPROPERTY('recql_ft_cat', 'ItemCount') AS count
                """
            )
            if row and int(row.get("status") or 0) == 0:
                return
        except Exception:
            return
        await asyncio.sleep(0.5)
