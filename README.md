# recql-playground

Interactive playground, demo suite, and dataset seeding for **RecQL**.

## Quickstart

### 🎮 Interactive Console Explorer

Launch the interactive terminal UI inside Docker (recommended) or on the local host to explore examples, edit parameters, modify queries live, and run them against any supported backend:

```bash
# Run inside Docker (starts database container and app automatically)
make menu
# or explicitly
make menu-docker
make menu-docker BACKEND=mssql
make menu-docker BACKEND=mongodb

# Run on local host python
make menu-local
# or
python -m examples.menu
```

The console UI lets you:
- **Select & Run Examples**: Hybrid search, personalized feeds, item-to-item similarity, CTR reranking, faceted filtering, pagination, and more.
- **Edit Parameters**: Interactively adjust query arguments (e.g. `user_id`, `query_text`, `limit`).
- **Edit Queries**: Modify query text live (inline or in `$EDITOR`) and immediately see ranked results.
- **View Query Plans**: Inspect the lowered JSON AST (`RankQueryConfig`).
- **Switch Databases**: Seamlessly switch between PostgreSQL, Microsoft SQL Server 2025, MongoDB, MariaDB, and Oracle 23ai.
- **Seed Databases**: Seed the MovieLens demo dataset into any backend.

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

# Personalized Feed
make example EXAMPLE=feeds/for_you BACKEND=postgres

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
# Start all database containers required for federation
make up-federated

# Seed databases
make seed-federated

# Run the federated example
make example-federated
```

---

### 🐳 Starting Database Containers

```bash
make up BACKEND=postgres
make up BACKEND=mssql
make up BACKEND=mongodb
make up BACKEND=mariadb
make up BACKEND=oracle
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
