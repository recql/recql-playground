"""Load a logical ``DemoCatalog`` into Oracle 26ai."""

from __future__ import annotations

import array
import json
from typing import Any

from examples.generator.catalog import DemoCatalog
from examples.generator.oracle.schema import apply_demo_schema


async def load_catalog(
    conn,
    catalog: DemoCatalog,
    *,
    engine_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await apply_demo_schema(
        conn, text_dims=catalog.text_dims, als_dims=catalog.als_dims
    )

    for it in catalog.items:
        attrs = json.dumps(it.attrs)
        cur = conn.cursor()
        try:
            await cur.execute(
                """
                MERGE INTO items t
                USING (SELECT :1 AS item_id FROM dual) s
                ON (t.item_id = s.item_id)
                WHEN MATCHED THEN UPDATE SET
                  attrs = :2, created_at = :3,
                  derived_popular_rank = :4, search_text = :5
                WHEN NOT MATCHED THEN INSERT
                  (item_id, attrs, created_at, derived_popular_rank, search_text)
                  VALUES (:6, :7, :8, :9, :10)
                """,
                [
                    it.item_id,
                    attrs,
                    it.created_at,
                    it.popular_rank,
                    it.search_text,
                    it.item_id,
                    attrs,
                    it.created_at,
                    it.popular_rank,
                    it.search_text,
                ],
            )
            await conn.commit()
        finally:
            cur.close()

    for u in catalog.users:
        attrs = json.dumps(u.attrs or {})
        cur = conn.cursor()
        try:
            await cur.execute(
                """
                MERGE INTO users t
                USING (SELECT :1 AS user_id FROM dual) s
                ON (t.user_id = s.user_id)
                WHEN NOT MATCHED THEN INSERT (user_id, attrs) VALUES (:2, :3)
                """,
                [u.user_id, u.user_id, attrs],
            )
            await conn.commit()
        finally:
            cur.close()

    for inter in catalog.interactions:
        cur = conn.cursor()
        try:
            await cur.execute(
                """
                MERGE INTO interactions t
                USING (SELECT :1 AS user_id, :2 AS item_id FROM dual) s
                ON (t.user_id = s.user_id AND t.item_id = s.item_id)
                WHEN MATCHED THEN UPDATE SET label = :3, created_at = COALESCE(:4, SYSTIMESTAMP)
                WHEN NOT MATCHED THEN INSERT
                  (user_id, item_id, label, created_at)
                  VALUES (:5, :6, :7, COALESCE(:8, SYSTIMESTAMP))
                """,
                [
                    inter.user_id,
                    inter.item_id,
                    inter.label,
                    inter.created_at,
                    inter.user_id,
                    inter.item_id,
                    inter.label,
                    inter.created_at,
                ],
            )
            await conn.commit()
        finally:
            cur.close()

    for emb in catalog.embeddings:
        vec = array.array("f", [float(x) for x in emb.vector])
        cur = conn.cursor()
        try:
            if emb.embedding_name == "als" and emb.entity_type == "user":
                await cur.execute(
                    """
                    MERGE INTO als_user_embeddings t
                    USING (SELECT :1 AS user_id FROM dual) s
                    ON (t.user_id = s.user_id)
                    WHEN MATCHED THEN UPDATE SET embedding = :2
                    WHEN NOT MATCHED THEN INSERT (user_id, embedding)
                      VALUES (:3, :4)
                    """,
                    [emb.entity_id, vec, emb.entity_id, vec],
                )
            elif emb.embedding_name == "als" and emb.entity_type == "item":
                await cur.execute(
                    """
                    MERGE INTO als_item_embeddings t
                    USING (SELECT :1 AS item_id FROM dual) s
                    ON (t.item_id = s.item_id)
                    WHEN MATCHED THEN UPDATE SET embedding = :2
                    WHEN NOT MATCHED THEN INSERT (item_id, embedding)
                      VALUES (:3, :4)
                    """,
                    [emb.entity_id, vec, emb.entity_id, vec],
                )
            else:
                await cur.execute(
                    """
                    MERGE INTO text_embeddings t
                    USING (
                      SELECT :1 AS embedding_name, :2 AS entity_id FROM dual
                    ) s
                    ON (t.embedding_name = s.embedding_name AND t.entity_id = s.entity_id)
                    WHEN MATCHED THEN UPDATE SET embedding = :3
                    WHEN NOT MATCHED THEN INSERT
                      (embedding_name, entity_id, embedding)
                      VALUES (:4, :5, :6)
                    """,
                    [
                        emb.embedding_name,
                        emb.entity_id,
                        vec,
                        emb.embedding_name,
                        emb.entity_id,
                        vec,
                    ],
                )
            await conn.commit()
        finally:
            cur.close()

    for model in catalog.models:
        spec = json.dumps(model.feature_spec)
        cur = conn.cursor()
        try:
            await cur.execute(
                """
                MERGE INTO models t
                USING (SELECT :1 AS name, :2 AS version FROM dual) s
                ON (t.name = s.name AND t.version = s.version)
                WHEN MATCHED THEN UPDATE SET
                  policy_type = :3, feature_spec = :4, blob = :5
                WHEN NOT MATCHED THEN INSERT
                  (name, policy_type, version, feature_spec, blob)
                  VALUES (:6, :7, :8, :9, :10)
                """,
                [
                    model.name,
                    model.version,
                    model.policy_type,
                    spec,
                    model.blob,
                    model.name,
                    model.policy_type,
                    model.version,
                    spec,
                    model.blob,
                ],
            )
            await conn.commit()
        finally:
            cur.close()

    return {
        "backend": "oracle",
        "items": len(catalog.items),
        "users": len(catalog.users),
        "interactions": len(catalog.interactions),
        "embeddings": len(catalog.embeddings),
        "models": len(catalog.models),
        **catalog.meta,
    }
