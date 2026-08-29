"""Interactive Console Menu UI for RecQL Playground.

Explore, edit, parameterize, and run RecQL examples against PostgreSQL,
Microsoft SQL Server 2025, MongoDB, MariaDB, or Oracle 23ai.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ANSI Color Codes
CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

DEFAULT_BACKENDS = {
    "postgres": {
        "name": "PostgreSQL (pgvector)",
        "dsn": os.environ.get("RECQL_PG_DSN", "postgres://recql:recql@127.0.0.1:55435/recql"),
        "container_dsn": "postgres://recql:recql@postgres:5432/recql",
    },
    "mssql": {
        "name": "Microsoft SQL Server 2025 (VECTOR + FTS)",
        "dsn": os.environ.get("RECQL_MSSQL_DSN", "mssql://sa:RecqlTest1234!@127.0.0.1:14333/recql"),
        "container_dsn": "mssql://sa:RecqlTest1234!@mssql:1433/recql",
    },
    "mongodb": {
        "name": "MongoDB 8.2+ ($vectorSearch + $search)",
        "dsn": os.environ.get("RECQL_MONGODB_DSN", "mongodb://127.0.0.1:27018/recql?directConnection=true"),
        "container_dsn": "mongodb://mongodb:27017/recql?directConnection=true",
    },
    "mariadb": {
        "name": "MariaDB 11.7+ (VECTOR + FULLTEXT)",
        "dsn": os.environ.get("RECQL_MARIADB_DSN", "mariadb://recql:recql@127.0.0.1:3306/recql"),
        "container_dsn": "mariadb://recql:recql@mariadb:3306/recql",
    },
    "oracle": {
        "name": "Oracle 23ai (VECTOR + Text)",
        "dsn": os.environ.get("RECQL_ORACLE_DSN", "oracle://recql:RecqlPass1@127.0.0.1:1521/FREEPDB1"),
        "container_dsn": "oracle://recql:RecqlPass1@oracle:1521/FREEPDB1",
    },
    "federated": {
        "name": "Federated Multi-DB (PostgreSQL + Oracle 23ai + MariaDB)",
        "dsn": "federated",
        "container_dsn": "federated",
    },
}

CATEGORIES = [
    (
        "Cross-Database / Federated",
        [
            ("federated", "Federated search & ranking (PostgreSQL + Oracle + MariaDB)"),
        ],
    ),
    (
        "Search & Discovery",
        [
            ("search/hybrid", "Hybrid search (Lexical + Vector RRF merge)"),
            ("search/semantic", "Semantic vector search with embeddings"),
            ("search/lexical", "Full-text lexical search"),
            ("search/personalized", "Personalized search (Query + User profile)"),
        ],
    ),
    (
        "Feeds & Recommendations",
        [
            ("feeds/for_you", "For You personalized feed (ALS + CTR Model)"),
            ("feeds/trending", "Trending items feed"),
            ("feeds/popular", "Most popular items"),
            ("feeds/new", "Newest item releases"),
        ],
    ),
    (
        "Similarity & Collaborative Filtering",
        [
            ("similar_items", "Item-to-item CF similarity (ALS i2i)"),
            ("similar_users", "User-to-user similarity"),
            ("complement_items", "Complementary items"),
        ],
    ),
    (
        "Reranking & Model Scoring",
        [
            ("reranking/model", "LightGBM CTR model reranking"),
            ("reranking/cross_encoder", "Cross-encoder scoring"),
            ("reranking/colbert", "ColBERT late-interaction scoring"),
            ("boosted", "Expression-based boosting & scoring"),
        ],
    ),
    (
        "Filters & Pagination",
        [
            ("pagination", "Seen-item tracking & KV pagination"),
            ("faceted_filtering", "Attribute & facet filtering"),
            ("filter_bubbles", "Filter bubbles / anti-concentration"),
        ],
    ),
]


def _in_container() -> bool:
    if os.environ.get("RECQL_IN_CONTAINER") in ("1", "true", "yes"):
        return True
    return Path("/app/examples/menu.py").is_file() and Path("/deps").is_dir()


def _get_default_dsn(backend: str) -> str:
    key = "container_dsn" if _in_container() else "dsn"
    return DEFAULT_BACKENDS.get(backend, {}).get(key, DEFAULT_BACKENDS["postgres"][key])


@dataclass
class PlaygroundState:
    backend: str = "postgres"
    dsn: str = ""
    encode: str = "st"  # st (384-d MiniLM) or fake (8-d)
    dims: int = 384

    def __post_init__(self):
        if not self.dsn:
            self.dsn = _get_default_dsn(self.backend)

    def engine_path(self) -> Path:
        st_suffix = ".st" if self.encode in ("st", "sentence_transformers") else ""
        eng = _EXAMPLES / "generator" / self.backend / f"engine{st_suffix}.yaml"
        if eng.is_file():
            return eng
        # Fallback to base engine.yaml
        return _EXAMPLES / "generator" / self.backend / "engine.yaml"


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _term_width() -> int:
    return max(70, min(shutil.get_terminal_size((80, 24)).columns, 110))


def _print_header(title: str = "RecQL Playground Console Explorer", state: PlaygroundState | None = None):
    w = _term_width()
    print(f"\n{CYAN}{'═' * w}{RESET}")
    print(f"{BOLD}{CYAN}  {title:^{w - 4}}  {RESET}")
    if state:
        bname = DEFAULT_BACKENDS.get(state.backend, {}).get("name", state.backend)
        enc_info = "MiniLM (384-d)" if state.encode in ("st", "sentence_transformers") else f"Fake ({state.dims}-d)"
        print(f"{DIM}  Target: {BOLD}{state.backend}{RESET}{DIM} ({bname}) | Encoder: {enc_info}{RESET}")
        print(f"{DIM}  DSN: {state.dsn}{RESET}")
    print(f"{CYAN}{'═' * w}{RESET}\n")


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
    raise FileNotFoundError(f"No query file for example {name!r}")


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
    if path is None or not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
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


async def _run_query(
    query_text: str,
    params: dict[str, Any],
    state: PlaygroundState,
    pagination_key: str | None = None,
) -> tuple[Any, float]:
    from recql.catalog import load_engine_catalog
    from recql.harness import recql
    from recql.plugins.connectors import open_connection, open_engine

    engine_path = state.engine_path()
    catalog = load_engine_catalog(engine_path) if engine_path.is_file() else None

    enc = "sentence_transformers" if state.encode in ("st", "sentence_transformers") else "fake"
    dims = 384 if enc == "sentence_transformers" else state.dims

    if state.backend == "federated" or (catalog and catalog.is_multi_backend()):
        registry, closer = await open_engine(
            catalog,
            dims=dims,
            encode_backend=enc,
        )
    else:
        registry, closer = await open_connection(
            state.dsn,
            backend=state.backend,
            catalog=catalog,
            dims=dims,
            encode_backend=enc,
        )
    t0 = time.perf_counter()
    try:
        res = await recql(
            engine=catalog or (str(engine_path) if engine_path.is_file() else None),
            query=query_text,
            params=params,
            backend=registry,
            pagination_key=pagination_key,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return res, elapsed_ms
    finally:
        if closer:
            await closer()


def _format_value(v: Any, max_len: int = 40) -> str:
    if isinstance(v, (dict, list)):
        s = json.dumps(v)
    else:
        s = str(v)
    if len(s) > max_len:
        return s[: max_len - 3] + "…"
    return s


def _display_results(result: Any, elapsed_ms: float):
    items = getattr(result, "items", [])
    w = _term_width()
    print(f"\n{GREEN}{BOLD}Query Results ({len(items)} items in {elapsed_ms:.2f}ms):{RESET}")
    print(f"{CYAN}{'─' * w}{RESET}")

    if not items:
        print(f"  {YELLOW}(No matching items found){RESET}")
    else:
        # Header
        print(f"  {BOLD}{'#':<3} {'ID':<10} {'Score':<10} {'Attributes / Title':<45}{RESET}")
        print(f"  {DIM}{'─'*3} {'─'*10} {'─'*10} {'─'*45}{RESET}")
        for i, cand in enumerate(items, 1):
            cid = cand.id
            score = f"{cand.retrieval_score:.4f}"
            attrs = cand.attributes or {}
            title = attrs.get("title") or attrs.get("movie_title") or ""
            other_keys = [f"{k}={_format_value(v, 20)}" for k, v in attrs.items() if k not in ("title", "movie_title")]
            extra_str = f" ({', '.join(other_keys)})" if other_keys else ""
            summary = (f"{title}" if title else "") + extra_str
            if not summary:
                summary = json.dumps(attrs) if attrs else "{}"
            if len(summary) > w - 28:
                summary = summary[: w - 31] + "…"
            print(f"  {i:<3} {cid:<10} {score:<10} {summary}")

    if getattr(result, "diagnostics", None):
        print(f"\n{DIM}Diagnostics: {'; '.join(result.diagnostics)}{RESET}")
    print(f"{CYAN}{'─' * w}{RESET}\n")


async def _seed_database(state: PlaygroundState, *, max_movies: int = 100, max_ratings: int = 4000):
    from examples.generator.run import run as run_generator

    enc = "sentence_transformers" if state.encode in ("st", "sentence_transformers") else "fake"
    dims = 384 if enc == "sentence_transformers" else state.dims

    print(f"\n{YELLOW}{BOLD}Starting database seeding for {state.backend}...{RESET}")
    print(f"  DSN: {state.dsn}")
    print(f"  Encoder: {enc} ({dims}-dimensional)")
    print(f"  Max movies: {max_movies}, Max ratings: {max_ratings}")

    t0 = time.perf_counter()
    try:
        ret = await run_generator(
            state.dsn,
            backend=state.backend,
            encode_backend=enc,
            dims=dims,
            max_movies=max_movies,
            max_ratings=max_ratings,
        )
        elapsed = time.perf_counter() - t0
        if ret == 0:
            print(f"{GREEN}{BOLD}✓ Seeding completed successfully in {elapsed:.2f}s!{RESET}\n")
        else:
            print(f"{RED}{BOLD}Seeding failed with exit code {ret}{RESET}\n")
    except Exception as exc:
        print(f"{RED}{BOLD}Seeding error:{RESET} {exc}")


def _edit_in_editor(initial_text: str, suffix: str = ".sql") -> str:
    editor = os.environ.get("EDITOR") or ("nano" if shutil.which("nano") else ("vim" if shutil.which("vim") else None))
    if not editor:
        print(f"{YELLOW}No $EDITOR found. Please enter new text (end with empty line or 'EOF'):{RESET}")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "EOF":
                    break
                lines.append(line)
            except EOFError:
                break
        return "\n".join(lines) if lines else initial_text

    with tempfile.NamedTemporaryFile("w+", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(initial_text)
        tmp_path = f.name

    try:
        subprocess.run([editor, tmp_path], check=True)
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


async def _run_example_interactive(example_name: str, desc: str, state: PlaygroundState):
    query_file = _find_query(example_name)
    params_file = _find_params(example_name, query_file)

    original_query = query_file.read_text(encoding="utf-8").strip()
    active_query = original_query
    active_params = _load_params(params_file)
    is_yaml = query_file.suffix.lower() == ".yaml"

    while True:
        _clear()
        _print_header(f"Example: {example_name}", state)
        print(f"{BOLD}Description:{RESET} {desc}")
        print(f"{BOLD}File:{RESET} {query_file.relative_to(_ROOT)}")

        print(f"\n{CYAN}{BOLD}Current Query ({query_file.suffix[1:].upper()}):{RESET}")
        for line in active_query.splitlines():
            print(f"  {line}")

        print(f"\n{CYAN}{BOLD}Current Parameters:{RESET}")
        if active_params:
            for k, v in active_params.items():
                print(f"  {BOLD}{k}{RESET} = {json.dumps(v)}")
        else:
            print(f"  {DIM}(No parameters needed / empty){RESET}")

        print(f"\n{MAGENTA}{'─' * _term_width()}{RESET}")
        print(f"{BOLD}Actions:{RESET}")
        print(f"  {GREEN}[1] Run Query{RESET} (or press Enter)")
        print(f"  {CYAN}[2] Edit Parameters{RESET}")
        print(f"  {YELLOW}[3] Edit Query{RESET}")
        print(f"  {BLUE}[4] View AST Query Plan{RESET}")
        print(f"  {MAGENTA}[5] Reset Query & Params to defaults{RESET}")
        print(f"  {RED}[0] Back to Example List{RESET}")

        choice = input(f"\n{BOLD}Select action [1]: {RESET}").strip()
        if choice in ("", "1", "r", "R"):
            print(f"\n{CYAN}Executing query...{RESET}")
            try:
                res, elapsed = await _run_query(active_query, active_params, state)
                _display_results(res, elapsed)
            except Exception as e:
                print(f"\n{RED}{BOLD}Execution Error:{RESET} {e}")
            input(f"{DIM}Press Enter to return to example menu...{RESET}")

        elif choice in ("2", "p", "P"):
            _clear()
            _print_header(f"Edit Parameters for {example_name}", state)
            print("Current parameters:")
            param_keys = list(active_params.keys())
            for idx, k in enumerate(param_keys, 1):
                print(f"  [{idx}] {BOLD}{k}{RESET} = {json.dumps(active_params[k])}")
            print(f"  [+] Add new parameter")
            print(f"  [0] Done editing")

            sel = input(f"\n{BOLD}Select parameter to edit (1-{len(param_keys)}, +, 0): {RESET}").strip()
            if sel == "+":
                new_k = input("Enter parameter name: ").strip()
                if new_k:
                    val_str = input(f"Enter value for {new_k} (JSON or raw string): ").strip()
                    try:
                        active_params[new_k] = json.loads(val_str)
                    except json.JSONDecodeError:
                        active_params[new_k] = val_str
            elif sel.isdigit():
                idx = int(sel)
                if 1 <= idx <= len(param_keys):
                    k = param_keys[idx - 1]
                    old_v = active_params[k]
                    val_str = input(f"Enter new value for {BOLD}{k}{RESET} [current: {json.dumps(old_v)}]: ").strip()
                    if val_str:
                        try:
                            active_params[k] = json.loads(val_str)
                        except json.JSONDecodeError:
                            active_params[k] = val_str

        elif choice in ("3", "e", "E"):
            _clear()
            _print_header(f"Edit Query for {example_name}", state)
            print(f"  [1] Open in $EDITOR ({os.environ.get('EDITOR', 'nano/vim')})")
            print(f"  [2] Quick single-line replacement")
            print(f"  [3] Paste entire query")
            print(f"  [0] Cancel")
            ech = input(f"\n{BOLD}Select edit method [1]: {RESET}").strip()
            if ech in ("", "1"):
                active_query = _edit_in_editor(active_query, suffix=".yaml" if is_yaml else ".sql")
            elif ech == "2":
                find_str = input("Find string: ")
                if find_str in active_query:
                    replace_str = input("Replace with: ")
                    active_query = active_query.replace(find_str, replace_str, 1)
                    print(f"{GREEN}Query updated!{RESET}")
                else:
                    print(f"{YELLOW}String not found in query.{RESET}")
                time.sleep(1)
            elif ech == "3":
                print(f"Paste your query below (type 'EOF' on a new line when done):")
                lines = []
                while True:
                    try:
                        l = input()
                        if l.strip() == "EOF":
                            break
                        lines.append(l)
                    except EOFError:
                        break
                if lines:
                    active_query = "\n".join(lines)

        elif choice in ("4", "v", "V"):
            from recql.harness import recql_to_rank_query_config

            _clear()
            _print_header(f"Query Plan for {example_name}", state)
            try:
                plan = recql_to_rank_query_config(active_query)
                print(json.dumps(plan, indent=2, default=str))
            except Exception as e:
                print(f"{RED}Plan error:{RESET} {e}")
            input(f"\n{DIM}Press Enter to return...{RESET}")

        elif choice in ("5", "m", "M"):
            active_query = original_query
            active_params = _load_params(params_file)
            print(f"{GREEN}Reset to defaults!{RESET}")
            time.sleep(0.8)

        elif choice in ("0", "b", "B", "q", "Q"):
            break


async def _switch_database_menu(state: PlaygroundState):
    while True:
        _clear()
        _print_header("Select Database Backend", state)

        keys = list(DEFAULT_BACKENDS.keys())
        for i, k in enumerate(keys, 1):
            info = DEFAULT_BACKENDS[k]
            mark = f" {GREEN}● ACTIVE{RESET}" if k == state.backend else ""
            print(f"  [{i}] {BOLD}{info['name']}{RESET}{mark}")
            print(f"      Default DSN: {DIM}{info['dsn']}{RESET}")

        print(f"  [6] Custom DSN / Connection String")
        print(f"  [7] Toggle Embeddings (Current: {'MiniLM 384-d' if state.encode in ('st', 'sentence_transformers') else 'Fake 8-d'})")
        print(f"  [0] Back to Main Menu")

        choice = input(f"\n{BOLD}Select option: {RESET}").strip()
        if choice in ("0", "b", "B", ""):
            break
        elif choice.isdigit() and 1 <= int(choice) <= len(keys):
            k = keys[int(choice) - 1]
            state.backend = k
            state.dsn = _get_default_dsn(k)
            print(f"{GREEN}Switched to {state.backend}!{RESET}")
            time.sleep(0.8)
            break
        elif choice == "6":
            new_dsn = input("Enter custom database DSN (e.g. postgres://... or mssql://...): ").strip()
            if new_dsn:
                state.dsn = new_dsn
                for bk in DEFAULT_BACKENDS:
                    if new_dsn.startswith(bk):
                        state.backend = bk
                        break
                print(f"{GREEN}Updated DSN to {state.dsn}!{RESET}")
                time.sleep(0.8)
                break
        elif choice == "7":
            if state.encode == "fake":
                state.encode = "st"
                state.dims = 384
            else:
                state.encode = "fake"
                state.dims = 8
            print(f"{GREEN}Encoder switched to {state.encode} ({state.dims}-d)!{RESET}")
            time.sleep(0.8)


async def _adhoc_repl(state: PlaygroundState):
    _clear()
    _print_header("Ad-hoc Query REPL", state)
    print("Enter any RecQL query (SQL or YAML).")
    print("Commands: ':quit' or ':q' to return | ':plan <query>' to view AST | ':params' to set params")
    print("-" * _term_width())

    params: dict[str, Any] = {}
    buf: list[str] = []

    while True:
        try:
            prompt = f"{CYAN}... {RESET}" if buf else f"{CYAN}recql [{state.backend}]> {RESET}"
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        sline = line.strip()
        if not buf and sline in (":quit", ":q", "exit", "quit"):
            break
        if not buf and sline == ":params":
            p_str = input("Enter params as JSON (e.g. {\"user_id\": \"55\"}): ").strip()
            if p_str:
                try:
                    params = json.loads(p_str)
                    print(f"{GREEN}Params updated:{RESET} {params}")
                except Exception as e:
                    print(f"{RED}JSON error:{RESET} {e}")
            continue
        if not buf and sline.startswith(":plan "):
            qtext = sline[6:].strip()
            try:
                from recql.harness import recql_to_rank_query_config
                print(json.dumps(recql_to_rank_query_config(qtext), indent=2, default=str))
            except Exception as e:
                print(f"{RED}Plan error:{RESET} {e}")
            continue

        buf.append(line)
        text = "\n".join(buf).strip()
        if text.endswith(";") or (not buf and (text.startswith("type:") or text.startswith("query:"))):
            pass
        elif sline == "" and buf:
            pass
        else:
            continue

        if text.endswith(";"):
            text = text[:-1].strip()
        buf.clear()

        if not text:
            continue

        try:
            res, elapsed = await _run_query(text, params, state)
            _display_results(res, elapsed)
        except Exception as e:
            print(f"{RED}Execution Error:{RESET} {e}\n")


async def async_main():
    # Detect initial backend from environment or args
    backend = os.environ.get("RECQL_BACKEND", "postgres")
    dsn = os.environ.get("RECQL_DATABASE") or _get_default_dsn(backend)
    encode = os.environ.get("RECQL_ENCODE", "st")
    dims = int(os.environ.get("RECQL_DIMS", "384" if encode in ("st", "sentence_transformers") else "8"))

    state = PlaygroundState(backend=backend, dsn=dsn, encode=encode, dims=dims)

    while True:
        _clear()
        _print_header("RecQL Playground Main Menu", state)

        flat_examples: list[tuple[str, str]] = []
        item_counter = 1

        for cat_title, items in CATEGORIES:
            print(f"{BOLD}{YELLOW}📂 {cat_title}{RESET}")
            for ex_name, ex_desc in items:
                flat_examples.append((ex_name, ex_desc))
                print(f"  {CYAN}[{item_counter:2d}]{RESET} {BOLD}{ex_name:<26}{RESET} {DIM}— {ex_desc}{RESET}")
                item_counter += 1
            print()

        print(f"{MAGENTA}{'─' * _term_width()}{RESET}")
        print(f"{BOLD}Management & Utilities:{RESET}")
        print(f"  {GREEN}[D] Switch Database / DSN{RESET} (Current: {state.backend})")
        print(f"  {YELLOW}[S] Seed Current Database{RESET} (MovieLens dataset)")
        print(f"  {BLUE}[R] Ad-hoc Query REPL{RESET}")
        print(f"  {RED}[Q] Exit{RESET}")

        choice = input(f"\n{BOLD}Select an example (1-{len(flat_examples)}) or option: {RESET}").strip()

        if choice.lower() in ("q", "quit", "exit", "0"):
            print(f"\n{GREEN}Goodbye!{RESET}\n")
            break
        elif choice.lower() in ("d", "db", "database"):
            await _switch_database_menu(state)
        elif choice.lower() in ("s", "seed"):
            _clear()
            _print_header("Seed Database", state)
            ans = input(f"Seed {BOLD}{state.backend}{RESET} at {state.dsn}? [Y/n]: ").strip()
            if ans.lower() not in ("n", "no"):
                await _seed_database(state)
                input(f"{DIM}Press Enter to continue...{RESET}")
        elif choice.lower() in ("r", "repl"):
            await _adhoc_repl(state)
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(flat_examples):
                ex_name, ex_desc = flat_examples[idx - 1]
                await _run_example_interactive(ex_name, ex_desc, state)


def main():
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")


if __name__ == "__main__":
    main()
