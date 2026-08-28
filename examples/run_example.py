#!/usr/bin/env python3
"""Run an examples/ use-case with MovieLens default params.

  python -m examples.run_example search/hybrid
  python -m examples.run_example feeds/for_you --backend mssql
  python -m examples.run_example feeds/for_you --seed 0
  python -m examples.run_example --list

From the host, `make example` / `make examples` invoke Docker automatically.
Use ``--local`` only with a dev venv and ``RECQL_USE_DOCKER=0``.

Resolves ``examples/<name>/query.{sql,yaml}`` (or ``examples/<dir>/<stem>.sql``)
and loads sibling ``params.yaml`` / ``<stem>.params.yaml``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CONTAINER_DSNS = {
    "postgres": "postgres://recql:recql@postgres:5432/recql",
    "oracle": "oracle://recql:RecqlPass1@oracle:1521/FREEPDB1",
    "mariadb": "mariadb://recql:recql@mariadb:3306/recql",
    "mongodb": "mongodb://mongodb:27017/recql?directConnection=true",
    "mssql": "mssql://sa:RecqlTest1234!@mssql:1433/recql",
}

_LOCAL_DSNS = {
    "postgres": os.environ.get("RECQL_PG_DSN", "postgres://recql:recql@127.0.0.1:55435/recql"),
    "oracle": os.environ.get("RECQL_ORACLE_DSN", "oracle://recql:RecqlPass1@127.0.0.1:1521/FREEPDB1"),
    "mariadb": os.environ.get("RECQL_MARIADB_DSN", "mariadb://recql:recql@127.0.0.1:3306/recql"),
    "mongodb": os.environ.get("RECQL_MONGODB_DSN", "mongodb://127.0.0.1:27018/recql?directConnection=true"),
    "mssql": os.environ.get("RECQL_MSSQL_DSN", "mssql://sa:RecqlTest1234!@127.0.0.1:14333/recql"),
}


def _in_container() -> bool:
    if os.environ.get("RECQL_IN_CONTAINER") in ("1", "true", "yes"):
        return True
    return Path("/app/recql").is_dir() and Path("/app/docker/app/entrypoint.sh").is_file()


def _cli_module() -> str:
    try:
        import recql_cli
        return "recql_cli"
    except ImportError:
        return "recql.cli"


def _seed_if_needed(args: argparse.Namespace, *, encode: str, backend: str) -> None:
    seed = os.environ.get("RECQL_SEED", getattr(args, "seed", "auto"))
    if str(seed).lower() in ("0", "false", "no"):
        return
    st = encode in ("st", "sentence_transformers", "hf", "minilm")
    encode_backend = "sentence_transformers" if st else "fake"
    dims = "384" if st else os.environ.get("RECQL_DIMS", "8")
    dsn = os.environ.get(
        "RECQL_DATABASE",
        _CONTAINER_DSNS.get(backend, _CONTAINER_DSNS["postgres"]),
    )
    import subprocess

    if str(seed).lower() != "force":
        chk = subprocess.run(
            [
                sys.executable,
                "-m",
                "examples.generator.check_seeded",
                "--backend",
                backend,
                "--database",
                dsn,
                "--dims",
                dims,
            ],
            capture_output=True,
        )
        if chk.returncode == 0:
            return

    print(f"seeding {backend} encode={encode_backend} dims={dims} …", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "examples.generator.run",
            "--backend",
            backend,
            "--database",
            dsn,
            "--encode-backend",
            encode_backend,
            "--dims",
            str(dims),
        ],
        check=True,
    )


def _find_query(name: str) -> Path:
    base = _EXAMPLES / name
    candidates = [
        base / "query.yaml",
        base / "query.sql",
        _EXAMPLES / f"{name}.yaml",
        _EXAMPLES / f"{name}.sql",
    ]
    if "/" in name:
        parent, leaf = name.rsplit("/", 1)
        candidates.extend(
            [
                _EXAMPLES / parent / f"{leaf}.yaml",
                _EXAMPLES / parent / f"{leaf}.sql",
            ]
        )
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"no query file for example {name!r}; tried: "
        + ", ".join(str(c) for c in candidates)
    )


def _find_params(name: str, query_path: Path) -> Path | None:
    base = query_path.parent
    stem = query_path.stem
    candidates = [
        base / "params.yaml",
        base / f"{stem}.params.yaml",
        query_path.with_name(f"{stem}.params.yaml"),
    ]
    if "/" in name:
        parent, leaf = name.rsplit("/", 1)
        candidates.insert(0, _EXAMPLES / parent / f"{leaf}.params.yaml")
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_params(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"params file must be a mapping: {path}")
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k.endswith("_id") or k.endswith("_ids") or k in ("user_id", "item_id"):
            if isinstance(v, list):
                out[k] = [str(x) for x in v]
            elif v is not None:
                out[k] = str(v)
            else:
                out[k] = v
        else:
            out[k] = v
    return out


def _cli_param_args(params: dict[str, Any]) -> list[str]:
    """Emit --param K=JSON so ids stay strings (CLI digit coerce otherwise)."""
    args: list[str] = []
    for k, v in params.items():
        args.extend(["--param", f"{k}={json.dumps(v)}"])
    return args


def _forward_args(args: argparse.Namespace) -> list[str]:
    """Extra CLI flags to pass through (not including params.yaml)."""
    out: list[str] = []
    for item in args.param:
        out.extend(["--param", item])
    return out


def list_examples() -> list[str]:
    found: set[str] = set()
    for p in list(_EXAMPLES.rglob("query.sql")) + list(_EXAMPLES.rglob("query.yaml")):
        rel = p.parent.relative_to(_EXAMPLES)
        if rel.parts and rel.parts[0] == "generator":
            continue
        found.add(str(rel))
    for p in (_EXAMPLES / "reranking").glob("*.sql"):
        found.add(f"reranking/{p.stem}")
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("example", nargs="?", help="e.g. search/hybrid, reranking/model")
    p.add_argument("--list", action="store_true")
    p.add_argument(
        "--backend",
        default=os.environ.get("RECQL_BACKEND", "postgres"),
        choices=("postgres", "oracle", "mariadb", "mongodb", "mssql"),
    )
    p.add_argument("--encode", default=os.environ.get("RECQL_ENCODE", "st"))
    p.add_argument("--seed", default=os.environ.get("RECQL_SEED", "0"))
    p.add_argument("--pagination-key", default=None)
    p.add_argument("--plan", action="store_true")
    p.add_argument("--param", action="append", default=[], help="Override K=V")
    p.add_argument("--print-only", action="store_true")
    p.add_argument(
        "--in-container",
        action="store_true",
        help="Run recql.cli inside the app container (no nested docker compose)",
    )
    p.add_argument(
        "--local",
        action="store_true",
        help="Use local Python CLI instead of docker compose",
    )
    args = p.parse_args(argv)

    in_container = args.in_container or _in_container()

    if args.list or not args.example:
        for name in list_examples():
            print(name)
        return 0 if args.list else 2

    query_path = _find_query(args.example)
    params_path = _find_params(args.example, query_path)
    params = _load_params(params_path)
    for item in args.param:
        if "=" not in item:
            print(f"invalid --param {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        try:
            params[k] = json.loads(v)
        except json.JSONDecodeError:
            params[k] = v

    encode = args.encode
    st = encode in ("st", "sentence_transformers", "hf", "minilm")
    eng_name = "engine.st.yaml" if st else "engine.yaml"
    backend_dir = args.backend
    container_engine = f"/app/examples/generator/{backend_dir}/{eng_name}"
    container_query = f"/app/{query_path.relative_to(_ROOT)}"

    print(
        f"example={args.example} query={query_path.relative_to(_ROOT)} "
        f"params={params_path.relative_to(_ROOT) if params_path else '∅'} → {params}",
        flush=True,
    )

    if in_container:
        _seed_if_needed(args, encode=encode, backend=args.backend)
        cmd = [
            sys.executable,
            "-m",
            _cli_module(),
            "--database",
            os.environ.get(
                "RECQL_DATABASE",
                _CONTAINER_DSNS.get(args.backend, _CONTAINER_DSNS["postgres"]),
            ),
            "--backend",
            args.backend,
            "--engine",
            os.environ.get("RECQL_ENGINE", container_engine),
            "--query-file",
            container_query,
            *_cli_param_args(params),
        ]
        if args.plan:
            cmd.append("--plan")
        if args.pagination_key:
            cmd.extend(["--pagination-key", args.pagination_key])
        if args.print_only:
            print(" ".join(cmd))
            return 0
        os.execvp(cmd[0], cmd)
        return 0

    if args.local or os.environ.get("RECQL_USE_DOCKER") in ("0", "false", "no"):
        dsn = (
            os.environ.get("RECQL_DATABASE")
            or _LOCAL_DSNS.get(args.backend, _LOCAL_DSNS["postgres"])
        )
        engine = str(_EXAMPLES / "generator" / backend_dir / eng_name)
        cmd = [
            sys.executable,
            "-m",
            _cli_module(),
            "--database",
            dsn,
            "--backend",
            args.backend,
            "--engine",
            engine,
            "--query-file",
            str(query_path),
            *_cli_param_args(params),
        ]
    else:
        service = f"app-{args.backend}"
        cmd = [
            "docker",
            "compose",
            "run",
            "--rm",
            "-e",
            f"RECQL_SEED={args.seed}",
            "-e",
            f"RECQL_ENCODE={encode}",
            "-e",
            f"RECQL_DIMS={'384' if st else '8'}",
            "--entrypoint",
            "python",
            service,
            "-m",
            "examples.run_example",
            args.example,
            "--in-container",
            "--encode",
            encode,
            "--backend",
            args.backend,
            *_forward_args(args),
        ]

    if args.plan:
        cmd.append("--plan")
    if args.pagination_key:
        cmd.extend(["--pagination-key", args.pagination_key])

    if args.print_only:
        print(" ".join(cmd))
        return 0

    os.chdir(_ROOT)
    os.execvp(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
