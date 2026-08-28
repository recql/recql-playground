"""Load a logical ``DemoCatalog`` into Microsoft SQL Server 2025."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from examples.generator.catalog import DemoCatalog, DemoEmbedding
from examples.generator.mssql.schema import apply_demo_schema, wait_fts_populated
from recql_mssql.db import MssqlDb, execute, vec_literal


async def load_catalog(
    db: Any,
    catalog: DemoCatalog,
    *,
    engine_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    d = db if isinstance(db, MssqlDb) else MssqlDb(db)
    await apply_demo_schema(
        d, text_dims=catalog.text_dims, als_dims=catalog.als_dims
    )

    for it in catalog.items:
        attrs_str = json.dumps(it.attrs or {})
        title = (it.attrs or {}).get("title") or (it.attrs or {}).get("movie_title") or ""
        created = (it.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            MERGE items WITH (HOLDLOCK) AS target
            USING (SELECT %s AS item_id, %s AS attrs, %s AS created_at, %s AS derived_popular_rank, %s AS search_text, %s AS title) AS src
            ON (target.item_id = src.item_id)
            WHEN MATCHED THEN
                UPDATE SET attrs = src.attrs, created_at = src.created_at, derived_popular_rank = src.derived_popular_rank, search_text = src.search_text, title = src.title
            WHEN NOT MATCHED THEN
                INSERT (item_id, attrs, created_at, derived_popular_rank, search_text, title)
                VALUES (src.item_id, src.attrs, src.created_at, src.derived_popular_rank, src.search_text, src.title);
        """
        await execute(d, sql, [it.item_id, attrs_str, created, it.popular_rank, it.search_text or "", title])

    for u in catalog.users:
        sql = """
            MERGE users WITH (HOLDLOCK) AS target
            USING (SELECT %s AS user_id, %s AS attrs) AS src
            ON (target.user_id = src.user_id)
            WHEN MATCHED THEN
                UPDATE SET attrs = src.attrs
            WHEN NOT MATCHED THEN
                INSERT (user_id, attrs)
                VALUES (src.user_id, src.attrs);
        """
        await execute(d, sql, [u.user_id, json.dumps(u.attrs or {})])

    for inter in catalog.interactions:
        created = (inter.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            MERGE interactions WITH (HOLDLOCK) AS target
            USING (SELECT %s AS user_id, %s AS item_id, %s AS label, %s AS created_at) AS src
            ON (target.user_id = src.user_id AND target.item_id = src.item_id)
            WHEN MATCHED THEN
                UPDATE SET label = src.label, created_at = src.created_at
            WHEN NOT MATCHED THEN
                INSERT (user_id, item_id, label, created_at)
                VALUES (src.user_id, src.item_id, src.label, src.created_at);
        """
        await execute(d, sql, [inter.user_id, inter.item_id, inter.label, created])

    for emb in catalog.embeddings:
        await _insert_embedding(d, emb)

    for model in catalog.models:
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            MERGE models WITH (HOLDLOCK) AS target
            USING (SELECT %s AS name, %s AS version, %s AS policy_type, %s AS feature_spec, CAST(%s AS VARBINARY(MAX)) AS blob_data, %s AS created_at) AS src
            ON (target.name = src.name AND target.version = src.version)
            WHEN MATCHED THEN
                UPDATE SET policy_type = src.policy_type, feature_spec = src.feature_spec, blob_data = src.blob_data, created_at = src.created_at
            WHEN NOT MATCHED THEN
                INSERT (name, version, policy_type, feature_spec, blob_data, created_at)
                VALUES (src.name, src.version, src.policy_type, src.feature_spec, src.blob_data, src.created_at);
        """
        await execute(
            d,
            sql,
            [
                model.name,
                model.version,
                model.policy_type,
                json.dumps(model.feature_spec),
                bytes(model.blob),
                created,
            ],
        )

    await wait_fts_populated(d)

    return {
        "backend": "mssql",
        "items": len(catalog.items),
        "users": len(catalog.users),
        "interactions": len(catalog.interactions),
        "embeddings": len(catalog.embeddings),
        "models": len(catalog.models),
        "text_dims": catalog.text_dims,
        "als_dims": catalog.als_dims,
        **catalog.meta,
        "engine_config": engine_config or {},
    }


async def _insert_embedding(db: MssqlDb, emb: DemoEmbedding) -> None:
    literal = vec_literal(emb.vector)
    dims = len(emb.vector)
    if emb.embedding_name == "als" and emb.entity_type == "user":
        sql = f"""
            MERGE als_user_embeddings WITH (HOLDLOCK) AS target
            USING (SELECT %s AS user_id, CAST(%s AS VECTOR({dims})) AS embedding) AS src
            ON (target.user_id = src.user_id)
            WHEN MATCHED THEN
                UPDATE SET embedding = src.embedding
            WHEN NOT MATCHED THEN
                INSERT (user_id, embedding)
                VALUES (src.user_id, src.embedding);
        """
        await execute(db, sql, [emb.entity_id, literal])
        return
    if emb.embedding_name == "als" and emb.entity_type == "item":
        sql = f"""
            MERGE als_item_embeddings WITH (HOLDLOCK) AS target
            USING (SELECT %s AS item_id, CAST(%s AS VECTOR({dims})) AS embedding) AS src
            ON (target.item_id = src.item_id)
            WHEN MATCHED THEN
                UPDATE SET embedding = src.embedding
            WHEN NOT MATCHED THEN
                INSERT (item_id, embedding)
                VALUES (src.item_id, src.embedding);
        """
        await execute(db, sql, [emb.entity_id, literal])
        return
    sql = f"""
        MERGE text_embeddings WITH (HOLDLOCK) AS target
        USING (SELECT %s AS embedding_name, %s AS entity_id, CAST(%s AS VECTOR({dims})) AS embedding) AS src
        ON (target.embedding_name = src.embedding_name AND target.entity_id = src.entity_id)
        WHEN MATCHED THEN
            UPDATE SET embedding = src.embedding
        WHEN NOT MATCHED THEN
            INSERT (embedding_name, entity_id, embedding)
            VALUES (src.embedding_name, src.entity_id, src.embedding);
    """
    await execute(db, sql, [emb.embedding_name, emb.entity_id, literal])
