"""Backend-agnostic demo catalog — MovieLens → load into any DB.

Logical items / users / interactions / embeddings / LightGBM blob.
Source: GroupLens ml-100k (same as https://github.com/ankane/movielens.sql).
Postgres / Oracle packages only *load* this catalog + ship engine.yaml.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from recql.encode import fake_embedding

from examples.generator.movielens import load_ml100k


@dataclass
class DemoItem:
    item_id: str
    title: str
    description: str
    created_at: datetime
    popular_rank: float
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return f"{self.title} {self.description}"


@dataclass
class DemoUser:
    user_id: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoInteraction:
    user_id: str
    item_id: str
    label: float
    created_at: datetime | None = None


@dataclass
class DemoEmbedding:
    embedding_name: str
    entity_type: str  # item | user
    entity_id: str
    vector: list[float]


@dataclass
class DemoModel:
    name: str
    policy_type: str
    version: str
    feature_spec: dict[str, Any]
    blob: bytes


@dataclass
class DemoCatalog:
    """Logical demo dataset shared by all backend loaders."""

    text_dims: int
    als_dims: int
    items: list[DemoItem]
    users: list[DemoUser]
    interactions: list[DemoInteraction]
    embeddings: list[DemoEmbedding]
    models: list[DemoModel]
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def dims(self) -> int:
        """Backward-compatible alias for text / semantic embedding width."""
        return self.text_dims


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if raw.strip().lower() in ("0", "none", "full", "all"):
        return None
    return int(raw)


def train_als_factors(
    interactions: list[tuple[str, str, float]],
    *,
    dims: int = 8,
    steps: int = 20,
    reg: float = 0.1,
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    users = sorted({u for u, _, _ in interactions})
    items = sorted({i for _, i, _ in interactions})
    if not users or not items:
        return {}, {}

    try:
        import numpy as np

        u_idx = {u: i for i, u in enumerate(users)}
        i_idx = {i: j for j, i in enumerate(items)}

        rng = np.random.RandomState(42)
        U = rng.randn(len(users), dims).astype(np.float32) * 0.1
        V = rng.randn(len(items), dims).astype(np.float32) * 0.1

        by_user: dict[int, list[tuple[int, float]]] = defaultdict(list)
        by_item: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for u, i, r in interactions:
            by_user[u_idx[u]].append((i_idx[i], float(r)))
            by_item[i_idx[i]].append((u_idx[u], float(r)))

        I_reg = np.eye(dims, dtype=np.float32) * float(reg)
        for _ in range(steps):
            for u, neigh in by_user.items():
                if not neigh:
                    continue
                v_sub = V[[j for j, _ in neigh]]
                r_sub = np.array([r for _, r in neigh], dtype=np.float32)
                xtx = v_sub.T @ v_sub + I_reg
                xty = v_sub.T @ r_sub
                U[u] = np.linalg.solve(xtx, xty)
            for i, neigh in by_item.items():
                if not neigh:
                    continue
                u_sub = U[[j for j, _ in neigh]]
                r_sub = np.array([r for _, r in neigh], dtype=np.float32)
                xtx = u_sub.T @ u_sub + I_reg
                xty = u_sub.T @ r_sub
                V[i] = np.linalg.solve(xtx, xty)

        return (
            {u: [float(x) for x in U[u_idx[u]]] for u in users},
            {i: [float(x) for x in V[i_idx[i]]] for i in items},
        )
    except ImportError:
        pass

    def zeros() -> list[float]:
        return [0.0] * dims

    U = {u: fake_embedding(f"u:{u}", dims=dims) for u in users}
    V = {i: fake_embedding(f"i:{i}", dims=dims) for i in items}
    by_user_py: dict[str, list[tuple[str, float]]] = defaultdict(list)
    by_item_py: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for u, i, r in interactions:
        by_user_py[u].append((i, r))
        by_item_py[i].append((u, r))

    def solve(target, neighbors, other):
        for key, neigh in neighbors.items():
            xtx = [[0.0] * dims for _ in range(dims)]
            xty = zeros()
            for oid, rating in neigh:
                vec = other[oid]
                for a in range(dims):
                    xty[a] += vec[a] * rating
                    for b in range(dims):
                        xtx[a][b] += vec[a] * vec[b]
            for a in range(dims):
                xtx[a][a] += reg
            target[key] = _solve(xtx, xty)

    for _ in range(steps):
        solve(U, by_user_py, V)
        solve(V, by_item_py, U)
    return U, V


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col] or 1e-12
        for j in range(col, n + 1):
            m[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            for j in range(col, n + 1):
                m[r][j] -= factor * m[col][j]
    return [m[i][n] for i in range(n)]


def _subsample_als(
    pairs: list[tuple[str, str, float]],
    *,
    max_users: int | None,
    max_items: int | None,
) -> list[tuple[str, str, float]]:
    if not pairs:
        return pairs
    user_counts: dict[str, int] = defaultdict(int)
    item_counts: dict[str, int] = defaultdict(int)
    for u, i, _ in pairs:
        user_counts[u] += 1
        item_counts[i] += 1
    keep_users = set(user_counts)
    keep_items = set(item_counts)
    # Always keep user 55 when present (recipe continuity)
    if max_users is not None and max_users > 0 and len(keep_users) > max_users:
        ranked = sorted(user_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        keep_users = {u for u, _ in ranked[:max_users]}
        if "55" in user_counts:
            keep_users.add("55")
    if max_items is not None and max_items > 0 and len(keep_items) > max_items:
        ranked = sorted(item_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        keep_items = {i for i, _ in ranked[:max_items]}
        keep_items.add("1")
    return [(u, i, r) for u, i, r in pairs if u in keep_users and i in keep_items]


def train_lightgbm_blob(
    interactions: list[DemoInteraction],
    items_by_id: dict[str, DemoItem],
    *,
    user_als: dict[str, list[float]] | None = None,
    item_als: dict[str, list[float]] | None = None,
    dims_hint: int = 4,
    max_rows: int | None = 5000,
) -> tuple[bytes, dict[str, Any]]:
    import lightgbm as lgb
    import numpy as np

    from recql.scoring import _dot

    U = user_als or {}
    V = item_als or {}
    rows = []
    labels = []
    for inter in interactions:
        it = items_by_id.get(inter.item_id)
        if it is None:
            continue
        als = _dot(U.get(inter.user_id, []), V.get(inter.item_id, []))
        rows.append(
            [
                float(als),
                float(it.popular_rank),
                float(len(str(it.attrs))),
            ]
        )
        labels.append(1 if float(inter.label) >= 3.0 else 0)
        if max_rows is not None and len(rows) >= max_rows:
            break
    if len(rows) < 2:
        X = np.array([[0.8, 1.0, 3.0], [0.2, 2.0, 1.0], [0.5, 3.0, 2.0], [0.1, 4.0, 1.0]])
        y = np.array([1, 0, 1, 0])
    else:
        X = np.array(rows, dtype=float)
        y = np.array(labels, dtype=int)
        if y.sum() == 0 or y.sum() == len(y):
            y = (X[:, 0] >= np.median(X[:, 0])).astype(int)

    feature_spec = {
        "features": ["als_score", "popular_rank", "attrs_len"],
        "dims": dims_hint,
    }
    train = lgb.Dataset(X, label=y, feature_name=feature_spec["features"])
    booster = lgb.train(
        {
            "objective": "binary",
            "verbosity": -1,
            "num_leaves": 8,
            "learning_rate": 0.1,
            "min_data_in_leaf": 1,
        },
        train,
        num_boost_round=20,
    )
    return booster.model_to_string().encode("utf-8"), feature_spec


def build_demo_catalog(
    *,
    dims: int = 8,
    encode_backend: str = "fake",
    with_als: bool = True,
    with_lgbm: bool = True,
    max_movies: int | None = None,
    max_ratings: int | None = None,
    als_max_users: int | None = None,
    als_max_items: int | None = None,
    als_steps: int | None = None,
    movielens_path: str | None = None,
    download: bool = True,
) -> DemoCatalog:
    """Build the logical demo dataset from MovieLens 100k (no database I/O).

    Limits default from env (unset = full set for Docker; CI/tests pass kwargs):

    - ``RECQL_MOVIELENS_MAX_MOVIES``
    - ``RECQL_MOVIELENS_MAX_RATINGS``
    - ``RECQL_ALS_MAX_USERS`` / ``RECQL_ALS_MAX_ITEMS`` / ``RECQL_ALS_STEPS``
    """
    if max_movies is None:
        max_movies = _env_int("RECQL_MOVIELENS_MAX_MOVIES", None)
    if max_ratings is None:
        max_ratings = _env_int("RECQL_MOVIELENS_MAX_RATINGS", None)
    if als_max_users is None:
        als_max_users = _env_int("RECQL_ALS_MAX_USERS", None)
    if als_max_items is None:
        als_max_items = _env_int("RECQL_ALS_MAX_ITEMS", None)
    if als_steps is None:
        als_steps = _env_int("RECQL_ALS_STEPS", 8) or 8

    bundle = load_ml100k(
        movielens_path,
        max_movies=max_movies,
        max_ratings=max_ratings,
        download=download,
    )

    rating_counts: dict[str, int] = defaultdict(int)
    for r in bundle.ratings:
        rating_counts[r.movie_id] += 1
    # Most-rated → popular_rank 1.0 (ASC column_order = popularity first)
    by_pop = sorted(
        rating_counts.items(), key=lambda kv: (-kv[1], int(kv[0]) if kv[0].isdigit() else kv[0])
    )
    popular_rank = {mid: float(i + 1) for i, (mid, _) in enumerate(by_pop)}

    items: list[DemoItem] = []
    for m in bundle.movies:
        genres = list(m.genres)
        genre_txt = ", ".join(genres) if genres else "film"
        desc = f"{m.title}. Genres: {genre_txt}."
        created = m.release_date or datetime(1995, 1, 1, tzinfo=timezone.utc)
        items.append(
            DemoItem(
                item_id=m.movie_id,
                title=m.title,
                description=desc,
                created_at=created,
                popular_rank=popular_rank.get(m.movie_id, float(len(items) + 1)),
                attrs={
                    "movie_title": m.title,
                    "title": m.title,
                    "description": desc,
                    "genre": genres[0] if genres else "Unknown",
                    "genres": genres,
                },
            )
        )
    items_by_id = {it.item_id: it for it in items}

    users = [
        DemoUser(
            user_id=u.user_id,
            attrs={
                k: v
                for k, v in {
                    "age": u.age,
                    "gender": u.gender,
                    "occupation": u.occupation,
                    "zip_code": u.zip_code,
                }.items()
                if v is not None
            },
        )
        for u in bundle.users
    ]

    interactions = [
        DemoInteraction(
            user_id=r.user_id,
            item_id=r.movie_id,
            label=r.rating,
            created_at=r.rated_at,
        )
        for r in bundle.ratings
        if r.movie_id in items_by_id
    ]

    embeddings: list[DemoEmbedding] = []
    text_encoder = None
    vector_dims = dims
    if encode_backend in ("sentence_transformers", "auto"):
        from recql.encode import get_encoder

        text_encoder = get_encoder(backend=encode_backend, dims=dims, warm=True)
        if getattr(text_encoder, "model_name", "") == "recql-fake":
            text_encoder = None
        else:
            vector_dims = int(text_encoder.dims)

    if text_encoder is not None:
        content_texts = [it.search_text for it in items]
        title_texts = [it.title for it in items]
        content_vecs = text_encoder.encode_many(content_texts)
        title_vecs = text_encoder.encode_many(title_texts)
        for it, cvec, tvec in zip(items, content_vecs, title_vecs, strict=True):
            embeddings.append(
                DemoEmbedding("content_embedding", "item", it.item_id, cvec)
            )
            embeddings.append(
                DemoEmbedding("title_embedding", "item", it.item_id, tvec)
            )
    else:
        for it in items:
            embeddings.append(
                DemoEmbedding(
                    "content_embedding",
                    "item",
                    it.item_id,
                    fake_embedding(it.search_text, dims=vector_dims),
                )
            )
            embeddings.append(
                DemoEmbedding(
                    "title_embedding",
                    "item",
                    it.item_id,
                    fake_embedding(it.title, dims=vector_dims),
                )
            )

    meta: dict[str, Any] = {
        "encode_backend": encode_backend if text_encoder else "fake",
        "dims": vector_dims,
        "text_encoder": getattr(text_encoder, "model_name", "recql-fake"),
        "movielens": dict(bundle.meta),
        "inspired_by": "https://github.com/ankane/movielens.sql",
    }

    U: dict[str, list[float]] = {}
    V: dict[str, list[float]] = {}
    als_dims = min(32, vector_dims) if vector_dims > 32 else vector_dims
    if with_als:
        als_map: dict[tuple[str, str], float] = {}
        for inter in interactions:
            als_map[(inter.user_id, inter.item_id)] = inter.label
        als_pairs = _subsample_als(
            [(u, i, r) for (u, i), r in als_map.items()],
            max_users=als_max_users,
            max_items=als_max_items,
        )
        U, V = train_als_factors(als_pairs, dims=als_dims, steps=als_steps)

        for uid, vec in U.items():
            embeddings.append(DemoEmbedding("als", "user", uid, vec))
        for iid, vec in V.items():
            embeddings.append(DemoEmbedding("als", "item", iid, vec))
        meta["als"] = {
            "users": len(U),
            "items": len(V),
            "pairs": len(als_pairs),
            "steps": als_steps,
            "factor_dims": als_dims,
        }

    models: list[DemoModel] = []
    if with_lgbm:
        blob, spec = train_lightgbm_blob(
            interactions, items_by_id, user_als=U, item_als=V
        )
        models.append(
            DemoModel(
                name="click_through_rate",
                policy_type="lightgbm",
                version="v1",
                feature_spec=spec,
                blob=blob,
            )
        )
        meta["lgbm"] = {"name": "click_through_rate", "n_rows": len(interactions)}

    return DemoCatalog(
        text_dims=vector_dims,
        als_dims=als_dims if with_als else vector_dims,
        items=items,
        users=users,
        interactions=interactions,
        embeddings=embeddings,
        models=models,
        meta=meta,
    )
