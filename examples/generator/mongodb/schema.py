"""Ensure MongoDB collections + Search / Vector Search indexes for the RecQL demo catalog."""

from __future__ import annotations

import asyncio
from typing import Any

from recql.errors import ExecuteError

TEXT_VECTOR_INDEX = "recql_text_vector"
ALS_ITEM_VECTOR_INDEX = "recql_als_item_vector"
ALS_USER_VECTOR_INDEX = "recql_als_user_vector"
ITEMS_SEARCH_INDEX = "recql_items_text"

_DEMO_COLLECTIONS = (
    "items",
    "users",
    "interactions",
    "text_embeddings",
    "als_user_embeddings",
    "als_item_embeddings",
    "models",
    "pagination_seen",
    "artifact_registry",
)


async def apply_demo_schema(db: Any, *, text_dims: int = 8, als_dims: int = 8) -> None:
    """Collections + B-tree indexes for the demo catalog."""
    await ensure_demo_base_schema(db)


async def ensure_demo_base_schema(db: Any) -> None:
    """Collections + B-tree indexes only (safe before / during data load)."""
    names = await db.list_collection_names()
    for name in _DEMO_COLLECTIONS:
        if name not in names:
            await db.create_collection(name)

    await db.items.create_index("item_id", unique=True)
    await db.items.create_index([("derived_popular_rank", 1)])
    await db.items.create_index([("created_at", -1)])

    await db.users.create_index("user_id", unique=True)
    await db.interactions.create_index(
        [("user_id", 1), ("item_id", 1)], unique=True
    )
    await db.text_embeddings.create_index(
        [("embedding_name", 1), ("entity_id", 1)], unique=True
    )
    await db.als_user_embeddings.create_index("user_id", unique=True)
    await db.als_item_embeddings.create_index("item_id", unique=True)
    await db.models.create_index([("name", 1), ("version", 1)], unique=True)
    await db.pagination_seen.create_index(
        [("page_key", 1), ("item_id", 1)], unique=True
    )
    await db.pagination_seen.create_index([("expires_at", 1)])


async def ensure_demo_search_indexes(db: Any, *, dims: int = 8) -> None:
    """Create Search / Vector Search indexes and wait until probe queries succeed."""
    await _ensure_vector_index(
        db.text_embeddings,
        TEXT_VECTOR_INDEX,
        path="embedding",
        dims=dims,
        filter_paths=["embedding_name"],
    )
    await _ensure_vector_index(
        db.als_item_embeddings,
        ALS_ITEM_VECTOR_INDEX,
        path="embedding",
        dims=dims,
    )
    await _ensure_vector_index(
        db.als_user_embeddings,
        ALS_USER_VECTOR_INDEX,
        path="embedding",
        dims=dims,
    )
    await _ensure_search_index(
        db.items,
        ITEMS_SEARCH_INDEX,
        paths=["search_text", "title", "description"],
    )
    await _wait_search_ready(db, dims=dims)


async def _existing_search_index_names(coll: Any) -> set[str]:
    try:
        cursor = await coll.list_search_indexes()
    except Exception:
        return set()
    names: set[str] = set()
    async for doc in cursor:
        name = doc.get("name")
        if name:
            names.add(str(name))
    return names


async def _ensure_vector_index(
    coll: Any,
    name: str,
    *,
    path: str,
    dims: int,
    filter_paths: list[str] | None = None,
) -> None:
    if name in await _existing_search_index_names(coll):
        return
    fields: list[dict[str, Any]] = [
        {
            "type": "vector",
            "path": path,
            "numDimensions": int(dims),
            "similarity": "cosine",
        }
    ]
    for fp in filter_paths or []:
        fields.append({"type": "filter", "path": fp})
    definition: dict[str, Any] = {"fields": fields}
    try:
        await coll.create_search_index(
            {"name": name, "type": "vectorSearch", "definition": definition}
        )
    except Exception as exc:
        msg = str(exc)
        if "already exists" in msg or "DuplicateIndex" in msg or "IndexAlreadyExists" in msg:
            return
        raise


async def _ensure_search_index(
    coll: Any,
    name: str,
    *,
    paths: list[str],
) -> None:
    if name in await _existing_search_index_names(coll):
        return
    fields: list[dict[str, Any]] = [{"type": "string", "path": p} for p in paths]
    definition = {"mappings": {"dynamic": False, "fields": {p: {"type": "string"} for p in paths}}}
    try:
        await coll.create_search_index(
            {"name": name, "type": "search", "definition": definition}
        )
    except Exception as exc:
        msg = str(exc)
        if "already exists" in msg or "DuplicateIndex" in msg or "IndexAlreadyExists" in msg:
            return
        raise


async def _probe_vector_search(
    coll: Any, index_name: str, dims: int, *, filter_doc: dict[str, Any] | None = None, require_hit: bool = True
) -> bool:
    probe_vec = [0.0] * int(dims)
    probe_vec[0] = 1.0
    if require_hit:
        sample = await coll.find_one(filter_doc or {})
        if sample and isinstance(sample.get("embedding"), (list, tuple)):
            raw_emb = sample["embedding"]
            if len(raw_emb) == dims:
                probe_vec = [float(x) for x in raw_emb]

    stage: dict[str, Any] = {
        "index": index_name,
        "path": "embedding",
        "queryVector": probe_vec,
        "numCandidates": 10,
        "limit": 1,
    }
    if filter_doc:
        stage["filter"] = filter_doc
    try:
        cursor = coll.aggregate([{"$vectorSearch": stage}, {"$limit": 1}])
        docs = await cursor.to_list(length=1)
        if require_hit:
            return len(docs) > 0
        return True
    except Exception:
        return False


async def _probe_text_search(coll: Any, index_name: str, *, require_hit: bool = True) -> bool:
    query_term = "Toy"
    if require_hit:
        sample = await coll.find_one({"search_text": {"$exists": True, "$ne": ""}})
        if sample:
            text = str(sample.get("search_text") or sample.get("title") or "")
            words = [w for w in text.replace("(", " ").replace(")", " ").split() if len(w) >= 3]
            if words:
                query_term = words[0]

    stage = {
        "index": index_name,
        "text": {
            "query": query_term,
            "path": ["search_text", "title", "description"],
        },
    }
    try:
        cursor = coll.aggregate([{"$search": stage}, {"$limit": 1}])
        docs = await cursor.to_list(length=1)
        if require_hit:
            return len(docs) > 0
        return True
    except Exception:
        return False


async def _wait_search_ready(db: Any, *, dims: int, timeout_s: float = 60.0, poll_interval_s: float = 1.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s

    text_count = await db.text_embeddings.count_documents({"embedding_name": "content_embedding"})
    als_item_count = await db.als_item_embeddings.count_documents({})
    als_user_count = await db.als_user_embeddings.count_documents({})
    items_count = await db.items.count_documents({})

    probes_config: list[tuple[str, Any]] = [
        (
            "text_embeddings vector",
            lambda: _probe_vector_search(
                db.text_embeddings,
                TEXT_VECTOR_INDEX,
                dims,
                filter_doc={"embedding_name": "content_embedding"},
                require_hit=text_count > 0,
            ),
        ),
        (
            "als_item_embeddings vector",
            lambda: _probe_vector_search(
                db.als_item_embeddings,
                ALS_ITEM_VECTOR_INDEX,
                dims,
                require_hit=als_item_count > 0,
            ),
        ),
        (
            "als_user_embeddings vector",
            lambda: _probe_vector_search(
                db.als_user_embeddings,
                ALS_USER_VECTOR_INDEX,
                dims,
                require_hit=als_user_count > 0,
            ),
        ),
        (
            "items text search",
            lambda: _probe_text_search(
                db.items,
                ITEMS_SEARCH_INDEX,
                require_hit=items_count > 0,
            ),
        ),
    ]

    pending = {name for name, _ in probes_config}

    while pending and asyncio.get_event_loop().time() < deadline:
        to_remove = set()
        for name, probe_fn in probes_config:
            if name not in pending:
                continue
            if await probe_fn():
                to_remove.add(name)
        pending -= to_remove
        if not pending:
            return
        await asyncio.sleep(poll_interval_s)

    if pending:
        raise ExecuteError(
            f"MongoDB Search indexes not ready after {timeout_s}s (still pending: {', '.join(sorted(pending))})"
        )
