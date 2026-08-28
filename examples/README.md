# RecQL examples

Runnable demos for the query-reference use cases against the **MovieLens 100k**
demo catalog (same source as [ankane/movielens.sql](https://github.com/ankane/movielens.sql)).

## Quick run

All via Docker (`make example` runs inside the app container):

```bash
make demo                          # hybrid search (sci-fi space adventure)
make example E=search/lexical      # uses examples/.../params.yaml
make example E=feeds/for_you
make example E=similar_items       # Toy Story (id 1) neighbors
make examples                    # list use-cases
```

Local tree is bind-mounted into the container — edit queries/code without rebuild.

Each use case ships a query plus MovieLens `params.yaml` (user **55**, item **1** =
Toy Story, etc.). Override: `make example E=search/hybrid ARGS='--param query_text=western'`.

## MovieLens param cheat sheet

| Param | Default | Meaning |
|---|---|---|
| `query_text` | `sci-fi space adventure` / `Star Wars` | Search text |
| `user_id` | `"55"` | ml-100k user |
| `item_id` / `seed_item_id` / `reference_item_id` | `"1"` | Toy Story |
| `genre` | `Animation` | Facet (also `genres` list on items) |
| `candidate_item_ids` | `1,50,100,181,258,286` | Popular titles for rerank |

## Use cases

| Directory | Use case |
|---|---|
| `generator/` | MovieLens → logical catalog + per-DB loaders + engine YAMLs |
| `search/` | Lexical / semantic / hybrid / personalized |
| `feeds/` | New, popular, trending, for you |
| `similar_items/` / `similar_users/` | i2i / u2u |
| `reranking/` | LightGBM / ColBERT / cross-encoder |
| `pagination/` | `pagination_key` exclusion |
| `complement_items/` | Multi-retrieve complements |
| `faceted_filtering/` | Genre facet via `array_has(genres, …)` |
| `filter_bubbles/` | Diversity / exploration |
| `boosted/` | Boosted reorder (ALS + Comedy promo bag) |

## Docker / encode

```bash
make demo ENCODE=st                # MiniLM (default)
make demo ENCODE=fake              # hash vectors (CI)
make example E=feeds/popular SEED=0
```

App container waits for the DB, seeds MovieLens when `RECQL_SEED=1`, then runs
`recql.cli` with `engine.st.yaml` (or `engine.yaml` for fake).

## Optional knobs

**pg_textsearch** (Postgres `engine.yaml`):

```yaml
index:
  lexical_search:
    enabled: true
    backend: auto   # auto | pg_textsearch | tsvector
```
