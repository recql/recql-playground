"""MovieLens 100k loader (same source as https://github.com/ankane/movielens.sql).

Downloads GroupLens ml-100k, parses ``u.item`` / ``u.user`` / ``u.data`` /
``u.genre``, and returns structures for ``build_demo_catalog``.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ML_100K_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"

# Genre flags in u.item columns 6.. (after unknown)
GENRE_NAMES = [
    "Action",
    "Adventure",
    "Animation",
    "Children's",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "Film-Noir",
    "Horror",
    "Musical",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]


@dataclass
class MovieLensMovie:
    movie_id: str
    title: str
    release_date: datetime | None
    genres: list[str] = field(default_factory=list)


@dataclass
class MovieLensUser:
    user_id: str
    age: int | None = None
    gender: str | None = None
    occupation: str | None = None
    zip_code: str | None = None


@dataclass
class MovieLensRating:
    user_id: str
    movie_id: str
    rating: float
    rated_at: datetime | None = None


@dataclass
class MovieLensBundle:
    movies: list[MovieLensMovie]
    users: list[MovieLensUser]
    ratings: list[MovieLensRating]
    meta: dict[str, Any] = field(default_factory=dict)


def cache_dir() -> Path:
    env = os.environ.get("RECQL_MOVIELENS_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "recql" / "movielens"


def ensure_ml100k(*, force: bool = False) -> Path:
    """Download + unzip ml-100k into cache; return path to extracted directory."""
    root = cache_dir()
    dest = root / "ml-100k"
    marker = dest / "u.item"
    if marker.exists() and not force:
        return dest
    root.mkdir(parents=True, exist_ok=True)
    zip_path = root / "ml-100k.zip"
    if force or not zip_path.exists():
        with urlopen(ML_100K_URL, timeout=120) as resp:
            zip_path.write_bytes(resp.read())
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(root)
    if not marker.exists():
        raise FileNotFoundError(f"ml-100k extract missing u.item under {root}")
    return dest


def load_ml100k(
    path: str | Path | None = None,
    *,
    max_movies: int | None = None,
    max_ratings: int | None = None,
    download: bool = True,
) -> MovieLensBundle:
    """Parse MovieLens 100k files (ankane/movielens.sql schema source)."""
    if path is None:
        if not download:
            raise FileNotFoundError("MovieLens path required when download=False")
        path = ensure_ml100k()
    base = Path(path)
    if (base / "u.item").exists():
        ml_dir = base
    elif (base / "ml-100k" / "u.item").exists():
        ml_dir = base / "ml-100k"
    else:
        raise FileNotFoundError(f"u.item not found under {base}")

    occupations: dict[str, str] = {}
    occ_file = ml_dir / "u.occupation"
    if occ_file.exists():
        for line in occ_file.read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name:
                occupations[name.lower()] = name.capitalize()

    users: list[MovieLensUser] = []
    for line in (ml_dir / "u.user").read_text(encoding="utf-8").splitlines():
        row = line.split("|")
        if len(row) < 5:
            continue
        occ = row[3]
        users.append(
            MovieLensUser(
                user_id=str(int(row[0])),
                age=int(row[1]),
                gender=row[2],
                occupation=occupations.get(occ.lower(), occ.capitalize()),
                zip_code=row[4],
            )
        )

    movies: list[MovieLensMovie] = []
    raw_items = (ml_dir / "u.item").read_bytes().decode("iso-8859-1").splitlines()
    for line in raw_items:
        row = line.split("|")
        if len(row) < 24:
            continue
        mid = str(int(row[0]))
        title = row[1].strip()
        release = None
        if row[2]:
            try:
                release = datetime.strptime(row[2], "%d-%b-%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                release = None
        # u.item: id|title|release|video|imdb|unknown|Action|... (18 genres)
        genres = []
        for i, name in enumerate(GENRE_NAMES):
            idx = 6 + i
            if idx < len(row) and row[idx] == "1":
                genres.append(name)
        movies.append(
            MovieLensMovie(
                movie_id=mid, title=title, release_date=release, genres=genres
            )
        )

    ratings: list[MovieLensRating] = []
    for line in (ml_dir / "u.data").read_text(encoding="utf-8").splitlines():
        row = line.split("\t")
        if len(row) < 4:
            continue
        ratings.append(
            MovieLensRating(
                user_id=str(int(row[0])),
                movie_id=str(int(row[1])),
                rating=float(row[2]),
                rated_at=datetime.fromtimestamp(int(row[3]), tz=timezone.utc),
            )
        )

    all_users_by_id = {u.user_id: u for u in users}

    if max_movies is not None and max_movies > 0:
        # Prefer most-rated movies so CF / popularity stay meaningful
        counts: dict[str, int] = {}
        for r in ratings:
            counts[r.movie_id] = counts.get(r.movie_id, 0) + 1
        keep = {
            mid
            for mid, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[
                :max_movies
            ]
        }
        # Always keep Toy Story (id 1) + item 3 for recipe / i2i test continuity
        keep.add("1")
        keep.add("3")
        movies = [m for m in movies if m.movie_id in keep]
        ratings = [r for r in ratings if r.movie_id in keep]

    if max_ratings is not None and max_ratings > 0 and len(ratings) > max_ratings:
        # Pin user 55 (recipe continuity) then fill with most recent ratings.
        pinned = [r for r in ratings if r.user_id == "55"]
        rest = [r for r in ratings if r.user_id != "55"]
        rest = sorted(
            rest,
            key=lambda r: (r.rated_at or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        budget = max(0, max_ratings - len(pinned))
        ratings = pinned + rest[:budget]

    used_users = {r.user_id for r in ratings}
    used_movies = {r.movie_id for r in ratings}
    # Recipe continuity: keep user 55 even if somehow unrated after filters
    used_users.add("55")
    movies = [m for m in movies if m.movie_id in used_movies]
    users = [
        all_users_by_id[uid]
        for uid in sorted(used_users, key=lambda x: int(x) if x.isdigit() else x)
        if uid in all_users_by_id
    ]
    for uid in used_users:
        if uid not in all_users_by_id:
            users.append(MovieLensUser(user_id=uid))

    return MovieLensBundle(
        movies=movies,
        users=users,
        ratings=ratings,
        meta={
            "source": "ml-100k",
            "url": ML_100K_URL,
            "inspired_by": "https://github.com/ankane/movielens.sql",
            "n_movies": len(movies),
            "n_users": len(users),
            "n_ratings": len(ratings),
            "path": str(ml_dir),
        },
    )


def write_ankane_style_sql(bundle: MovieLensBundle, out: Path | None = None) -> str:
    """Emit INSERT SQL similar to ankane/movielens.sql (Postgres-friendly)."""
    def q(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, datetime):
            return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        return str(v)

    lines = ["BEGIN;"]
    lines.append("DROP TABLE IF EXISTS genres_movies;")
    lines.append("DROP TABLE IF EXISTS genres;")
    lines.append("DROP TABLE IF EXISTS ratings;")
    lines.append("DROP TABLE IF EXISTS movies;")
    lines.append("DROP TABLE IF EXISTS users;")
    lines.append("DROP TABLE IF EXISTS occupations;")
    lines.append(
        "CREATE TABLE occupations (id integer PRIMARY KEY, name varchar(255));"
    )
    lines.append(
        "CREATE TABLE users (id integer PRIMARY KEY, age integer, gender char(1), "
        "occupation_id integer, zip_code varchar(255));"
    )
    lines.append(
        "CREATE TABLE movies (id integer PRIMARY KEY, title varchar(255), release_date date);"
    )
    lines.append(
        "CREATE TABLE ratings (id integer PRIMARY KEY, user_id integer, movie_id integer, "
        "rating integer, rated_at timestamp);"
    )
    lines.append("CREATE TABLE genres (id integer PRIMARY KEY, name varchar(255));")
    lines.append(
        "CREATE TABLE genres_movies (id integer PRIMARY KEY, movie_id integer, genre_id integer);"
    )

    occs = sorted({(u.occupation or "other") for u in bundle.users})
    occ_id = {name: i + 1 for i, name in enumerate(occs)}
    for name, i in occ_id.items():
        lines.append(f"INSERT INTO occupations VALUES ({i},{q(name)});")

    for u in bundle.users:
        lines.append(
            "INSERT INTO users VALUES ("
            f"{int(u.user_id)},{u.age or 'NULL'},{q(u.gender)},"
            f"{occ_id.get(u.occupation or 'other')},{q(u.zip_code)});"
        )

    genre_id = {name: i + 1 for i, name in enumerate(GENRE_NAMES)}
    for name, i in genre_id.items():
        lines.append(f"INSERT INTO genres VALUES ({i},{q(name)});")

    for m in bundle.movies:
        rd = m.release_date.strftime("%Y-%m-%d") if m.release_date else None
        lines.append(
            f"INSERT INTO movies VALUES ({int(m.movie_id)},{q(m.title)},{q(rd)});"
        )
        for g in m.genres:
            gid = genre_id[g]
            lines.append(
                f"INSERT INTO genres_movies VALUES "
                f"(DEFAULT,{int(m.movie_id)},{gid});"
            )

    for i, r in enumerate(bundle.ratings, start=1):
        lines.append(
            "INSERT INTO ratings VALUES ("
            f"{i},{int(r.user_id)},{int(r.movie_id)},{int(r.rating)},"
            f"{q(r.rated_at)});"
        )
    lines.append("COMMIT;")
    sql = "\n".join(lines) + "\n"
    # Fix DEFAULT for sqlite/pg — use sequential ids for genres_movies
    fixed: list[str] = []
    gm = 0
    for line in sql.splitlines():
        if "INSERT INTO genres_movies VALUES (DEFAULT," in line:
            gm += 1
            line = line.replace("(DEFAULT,", f"({gm},", 1)
        fixed.append(line)
    sql = "\n".join(fixed) + "\n"
    if out is not None:
        out.write_text(sql, encoding="utf-8")
    return sql
