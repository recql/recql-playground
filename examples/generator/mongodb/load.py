"""Load a logical ``DemoCatalog`` into MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson.binary import Binary

from examples.generator.catalog import DemoCatalog, DemoEmbedding
from examples.generator.mongodb.schema import apply_demo_schema, ensure_demo_search_indexes


async def load_catalog(
    db,
    catalog: DemoCatalog,
    *,
    engine_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await apply_demo_schema(db, text_dims=catalog.text_dims, als_dims=catalog.als_dims)

    for it in catalog.items:
        await db.items.update_one(
            {"item_id": it.item_id},
            {
                "$set": {
                    "item_id": it.item_id,
                    "attrs": it.attrs or {},
                    "created_at": it.created_at or datetime.now(timezone.utc),
                    "derived_popular_rank": it.popular_rank,
                    "search_text": it.search_text or "",
                    "title": (it.attrs or {}).get("title")
                    or (it.attrs or {}).get("movie_title")
                    or "",
                    "description": (it.attrs or {}).get("description") or "",
                    "genre": (it.attrs or {}).get("genre") or "",
                }
            },
            upsert=True,
        )

    for u in catalog.users:
        await db.users.update_one(
            {"user_id": u.user_id},
            {"$set": {"user_id": u.user_id, "attrs": u.attrs or {}}},
            upsert=True,
        )

    for inter in catalog.interactions:
        await db.interactions.update_one(
            {"user_id": inter.user_id, "item_id": inter.item_id},
            {
                "$set": {
                    "user_id": inter.user_id,
                    "item_id": inter.item_id,
                    "label": inter.label,
                    "created_at": inter.created_at or datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    for emb in catalog.embeddings:
        await _upsert_embedding(db, emb)

    for model in catalog.models:
        await db.models.update_one(
            {"name": model.name, "version": model.version},
            {
                "$set": {
                    "name": model.name,
                    "policy_type": model.policy_type,
                    "version": model.version,
                    "feature_spec": model.feature_spec,
                    "blob": Binary(bytes(model.blob)),
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    await ensure_demo_search_indexes(db, dims=catalog.text_dims)

    return {
        "backend": "mongodb",
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


async def _upsert_embedding(db, emb: DemoEmbedding) -> None:
    vec = list(emb.vector)
    if emb.embedding_name == "als" and emb.entity_type == "user":
        await db.als_user_embeddings.update_one(
            {"user_id": emb.entity_id},
            {"$set": {"user_id": emb.entity_id, "embedding": vec}},
            upsert=True,
        )
        return
    if emb.embedding_name == "als" and emb.entity_type == "item":
        await db.als_item_embeddings.update_one(
            {"item_id": emb.entity_id},
            {"$set": {"item_id": emb.entity_id, "embedding": vec}},
            upsert=True,
        )
        return
    await db.text_embeddings.update_one(
        {"embedding_name": emb.embedding_name, "entity_id": emb.entity_id},
        {
            "$set": {
                "embedding_name": emb.embedding_name,
                "entity_id": emb.entity_id,
                "embedding": vec,
            }
        },
        upsert=True,
    )
