# recql-playground

Interactive playground, demo suite, and dataset seeding for **RecQL**.

## Prerequisites & Directory Structure

`recql-playground` mounts and installs the sibling RecQL repositories in editable mode into the development environment/containers. To run the playground locally or with Docker, clone all the companion repositories side-by-side in the same parent directory:

```bash
mkdir recql-workspace && cd recql-workspace

# Clone core engine and CLI
git clone git@github.com:recql/recql-python-core.git
git clone git@github.com:recql/recql-python-cli.git

# Clone backend database adapters
git clone git@github.com:recql/recql-python-postgres.git
git clone git@github.com:recql/recql-python-oracle.git
git clone git@github.com:recql/recql-python-mariadb.git
git clone git@github.com:recql/recql-python-mssql.git
git clone git@github.com:recql/recql-python-mongodb.git

# Clone the playground
git clone git@github.com:recql/recql-playground.git
cd recql-playground
```

### Directory Layout

```text
recql-workspace/
├── recql-playground/       # Playground runner & MovieLens demo suite (you are here)
├── recql-python-core/       # Core AST parser, OpenAPI IR, pipeline executor & query optimizer
├── recql-python-cli/        # CLI client and REPL
├── recql-python-postgres/   # PostgreSQL + pgvector adapter
├── recql-python-oracle/     # Oracle 23ai AI Vector Search adapter
├── recql-python-mariadb/    # MariaDB 11.7+ vector & fulltext adapter
├── recql-python-mssql/      # Microsoft SQL Server 2025 vector & fulltext adapter
└── recql-python-mongodb/    # MongoDB 8.2+ Atlas / Community vector & text search adapter
```

*(Optional: If your directories live elsewhere, you can override their paths via environment variables: `RECQL_CORE_PATH`, `RECQL_CLI_PATH`, `RECQL_POSTGRES_PATH`, `RECQL_ORACLE_PATH`, `RECQL_MARIADB_PATH`, `RECQL_MSSQL_PATH`, `RECQL_MONGODB_PATH`)*

---

## Quickstart

### 🎮 Interactive Console Explorer

Launch the interactive terminal UI inside Docker (recommended) or on the local host to explore examples, edit parameters, modify queries live, and run them against any supported backend:

```bash
# Run inside Docker (starts database container and app automatically)
make menu
# or explicitly
make menu-docker
make menu-docker BACKEND=postgres
make menu-docker BACKEND=oracle
make menu-docker BACKEND=mariadb
make menu-docker BACKEND=mssql
make menu-docker BACKEND=mongodb
make menu-docker BACKEND=federated

# Run on local host python
make menu-local
# or
python -m examples.menu
```

The console UI lets you:
- **Select & Run Examples**: Hybrid search, personalized feeds, interaction pooling, item-to-item similarity, CTR reranking, faceted filtering, pagination, and cross-database federation.
- **Edit Parameters**: Interactively adjust query arguments (e.g. `user_id`, `query_text`, `limit`).
- **Edit Queries**: Modify query text live (inline or in `$EDITOR`) and immediately see ranked results.
- **View Query Plans**: Inspect the lowered JSON AST (`RankQueryConfig`).
- **Switch Databases**: Seamlessly switch between PostgreSQL, Microsoft SQL Server 2025, MongoDB, MariaDB, Oracle 23ai, and Federated Multi-DB.
- **Seed Databases**: Seed the MovieLens demo dataset into any backend (or all federated backends).

---

### 🌱 Seeding Databases

Seed the MovieLens demo catalog into any database backend using the `Makefile`:

```bash
# Seed in Docker
make seed-docker BACKEND=postgres
make seed-docker BACKEND=mssql
make seed-docker BACKEND=mongodb

# Seed on local host
make seed
make seed-postgres
make seed-mssql
make seed-mongodb
make seed-mariadb
make seed-oracle

# Or pass custom variables
make seed BACKEND=mssql DATABASE="mssql://sa:RecqlTest1234!@127.0.0.1:14333/recql" DIMS=8
```

---

### 🚀 Running Specific Examples

Run any individual example directly from the command line:

```bash
# Hybrid Search (Lexical + Vector)
make example EXAMPLE=search/hybrid BACKEND=mssql

# Personalized Feed (Precomputed user ALS)
make example EXAMPLE=feeds/for_you BACKEND=postgres

# Interaction Pooling Feed (Dynamic aggregation of recent item vectors)
make example EXAMPLE=feeds/interaction_pooling BACKEND=postgres

# Similar Items (Item-to-Item CF)
make example EXAMPLE=similar_items BACKEND=mariadb

# Cross-Database Federated Search (PostgreSQL + Oracle 23ai + MariaDB)
make example-federated
# or explicitly inside Docker:
make example-federated-docker

# List all available examples
make example
```

---

### 🌐 Cross-Database (Federated) Queries

RecQL can federate across multiple databases in parallel within a single query:

- **Oracle 23ai**: AI Vector Search semantic ANN retrieval (`content_embedding`)
- **PostgreSQL**: Collaborative filtering ALS user vectors & relations
- **MariaDB**: FullText BM25 lexical keyword matching
- **PostgreSQL**: Interaction history filtering (`exclude_seen`) and LightGBM model scoring

```bash
# Running in Docker (automatic DB startup & seeding):
make example-federated
# or launch the menu:
make menu-docker BACKEND=federated

# Running on local host:
make up-federated       # Start postgres + oracle + mariadb containers
make seed-federated     # Seed all 3 databases
make example-federated-local
```

---

### 🐳 Starting Database Containers

```bash
make up BACKEND=postgres
make up BACKEND=mssql
make up BACKEND=mongodb
make up BACKEND=mariadb
make up BACKEND=oracle
make up-federated
```

---

## Supported Backends

| Backend | Vector Search | Lexical Search | Default DSN |
|---|---|---|---|
| **PostgreSQL** | `pgvector` (`cosine`) | `tsvector` / `tsquery` | `postgres://recql:recql@127.0.0.1:55435/recql` |
| **Microsoft SQL Server 2025** | `VECTOR(N)` / `VECTOR_DISTANCE` | Full-Text Search (`CONTAINSTABLE`) | `mssql://sa:RecqlTest1234!@127.0.0.1:14333/recql` |
| **MongoDB 8.2+** | `$vectorSearch` | `$search` | `mongodb://127.0.0.1:27018/recql?directConnection=true` |
| **MariaDB 11.7+** | `VECTOR` / `VEC_DISTANCE_COSINE` | `MATCH ... AGAINST` | `mariadb://recql:recql@127.0.0.1:3306/recql` |
| **Oracle 23ai** | `VECTOR` / `VECTOR_DISTANCE` | Oracle Text (`CONTAINS`) | `oracle://recql:RecqlPass1@127.0.0.1:1521/FREEPDB1` |
| **Federated Multi-DB** | Routed per vector/store | Routed per index config | `federated` (composite engine) |
