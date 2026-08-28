.DEFAULT_GOAL := help

PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
COMPOSE ?= docker compose

# Default target backend: postgres | mssql | mongodb | mariadb | oracle
BACKEND ?= postgres
ENCODE ?= st
DIMS ?= 384
SEED ?= auto
MAX_MOVIES ?= 100
MAX_RATINGS ?= 4000
RECQL_USE_DOCKER ?= 1

# Sibling checkout directories (mounted into app containers)
RECQL_CORE_PATH ?= ../recql-python-core
RECQL_CLI_PATH ?= ../recql-python-cli
RECQL_POSTGRES_PATH ?= ../recql-python-postgres
RECQL_MSSQL_PATH ?= ../recql-python-mssql
RECQL_MONGODB_PATH ?= ../recql-python-mongodb
RECQL_MARIADB_PATH ?= ../recql-python-mariadb
RECQL_ORACLE_PATH ?= ../recql-python-oracle

# Default local host connection DSNs
PG_DSN ?= postgres://recql:recql@127.0.0.1:55435/recql
MSSQL_DSN ?= mssql://sa:RecqlTest1234!@127.0.0.1:14333/recql
MONGODB_DSN ?= mongodb://127.0.0.1:27018/recql?directConnection=true
MARIADB_DSN ?= mariadb://recql:recql@127.0.0.1:3306/recql
ORACLE_DSN ?= oracle://recql:RecqlPass1@127.0.0.1:1521/FREEPDB1

ifeq ($(BACKEND),mssql)
  DATABASE ?= $(MSSQL_DSN)
else ifeq ($(BACKEND),mongodb)
  DATABASE ?= $(MONGODB_DSN)
else ifeq ($(BACKEND),mariadb)
  DATABASE ?= $(MARIADB_DSN)
else ifeq ($(BACKEND),oracle)
  DATABASE ?= $(ORACLE_DSN)
else
  DATABASE ?= $(PG_DSN)
endif

export RECQL_BACKEND = $(BACKEND)
export RECQL_DATABASE = $(DATABASE)
export RECQL_ENCODE = $(ENCODE)
export RECQL_DIMS = $(DIMS)
export RECQL_SEED = $(SEED)
export RECQL_CORE_PATH
export RECQL_CLI_PATH
export RECQL_POSTGRES_PATH
export RECQL_MSSQL_PATH
export RECQL_MONGODB_PATH
export RECQL_MARIADB_PATH
export RECQL_ORACLE_PATH
export RECQL_PG_DSN = $(PG_DSN)
export RECQL_MSSQL_DSN = $(MSSQL_DSN)
export RECQL_MONGODB_DSN = $(MONGODB_DSN)
export RECQL_MARIADB_DSN = $(MARIADB_DSN)
export RECQL_ORACLE_DSN = $(ORACLE_DSN)

.PHONY: help menu run menu-docker run-docker menu-local run-local build build-app \
        seed seed-docker seed-local seed-postgres seed-mssql seed-mongodb seed-mariadb seed-oracle \
        example repl up down reset up-postgres up-mssql up-mongodb up-mariadb up-oracle

help: ## Show targets and descriptions
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[1mConfigurable variables:\033[0m\n'
	@printf '  BACKEND          Target database (\033[33mpostgres\033[0m | \033[33mmssql\033[0m | \033[33mmongodb\033[0m | \033[33mmariadb\033[0m | \033[33moracle\033[0m) [default: $(BACKEND)]\n'
	@printf '  DATABASE         Database DSN [default: $(DATABASE)]\n'
	@printf '  ENCODE           Embedding encoder (\033[33mfake\033[0m | \033[33mst\033[0m) [default: $(ENCODE)]\n'
	@printf '  DIMS             Vector dimensions [default: $(DIMS)]\n'
	@printf '  SEED             Seed on start in container (1/0) [default: $(SEED)]\n'
	@printf '\n\033[1mUsage examples:\033[0m\n'
	@printf '  make menu-docker                   # Run interactive menu inside Docker container\n'
	@printf '  make menu-docker BACKEND=mssql     # Run menu in Docker targeting SQL Server 2025\n'
	@printf '  make menu-docker BACKEND=mongodb   # Run menu in Docker targeting MongoDB\n'
	@printf '  make menu-local                    # Run menu on local host python\n'
	@printf '  make seed BACKEND=mssql            # Seed SQL Server 2025\n'
	@printf '  make example EXAMPLE=search/hybrid # Run a specific example\n'

menu: ## Launch console menu UI (Docker by default, local if RECQL_USE_DOCKER=0)
ifeq ($(RECQL_USE_DOCKER),0)
	@$(MAKE) menu-local
else
	@$(MAKE) menu-docker
endif

run: menu ## Alias for make menu

menu-docker: ## Launch console menu UI inside Docker container (auto-starts DB)
	$(COMPOSE) run --rm -it \
	  -e RECQL_BACKEND=$(BACKEND) \
	  -e RECQL_ENCODE=$(ENCODE) \
	  -e RECQL_DIMS=$(DIMS) \
	  -e RECQL_SEED=$(SEED) \
	  app-$(BACKEND) \
	  --menu

run-docker: menu-docker ## Alias for make menu-docker

menu-local: ## Launch console menu UI on local host
	@$(PYTHON) -m examples.menu

run-local: menu-local ## Alias for make menu-local

build: build-app ## Build Docker image

build-app: ## Build recql-playground app image
	$(COMPOSE) build app-$(BACKEND)

seed: ## Seed the target database on host (BACKEND=postgres|mssql|mongodb|mariadb|oracle)
	@echo "Seeding $(BACKEND) at $(DATABASE) (encode=$(ENCODE), dims=$(DIMS)) …"
	@$(PYTHON) -m examples.generator.run \
	  --backend $(BACKEND) \
	  --database "$(DATABASE)" \
	  --encode-backend $(ENCODE) \
	  --dims $(DIMS) \
	  --max-movies $(MAX_MOVIES) \
	  --max-ratings $(MAX_RATINGS)

seed-docker: ## Seed target database inside Docker container (forces re-seed)
	$(COMPOSE) run --rm \
	  -e RECQL_BACKEND=$(BACKEND) \
	  -e RECQL_ENCODE=$(ENCODE) \
	  -e RECQL_DIMS=$(DIMS) \
	  -e RECQL_SEED=force \
	  app-$(BACKEND) \
	  -c "SELECT 1" >/dev/null 2>&1 || true
	@echo "Seeded $(BACKEND) in Docker!"

seed-local: seed ## Alias for local seed

seed-postgres: ## Seed PostgreSQL database
	@$(MAKE) seed BACKEND=postgres

seed-mssql: ## Seed Microsoft SQL Server 2025 database
	@$(MAKE) seed BACKEND=mssql

seed-mongodb: ## Seed MongoDB database
	@$(MAKE) seed BACKEND=mongodb

seed-mariadb: ## Seed MariaDB database
	@$(MAKE) seed BACKEND=mariadb

seed-oracle: ## Seed Oracle 23ai database
	@$(MAKE) seed BACKEND=oracle

example: ## Run a specific example (e.g. make example EXAMPLE=search/hybrid BACKEND=postgres)
	@if [ -z "$(EXAMPLE)" ]; then \
	  echo "Usage: make example EXAMPLE=<name> [BACKEND=postgres|mssql|mongodb|mariadb|oracle]"; \
	  echo "Examples:"; \
	  $(PYTHON) -m examples.run_example --list; \
	  exit 1; \
	fi
	@if [ "$(RECQL_USE_DOCKER)" = "1" ]; then \
	  $(COMPOSE) run --rm \
	    -e RECQL_BACKEND=$(BACKEND) \
	    -e RECQL_ENCODE=$(ENCODE) \
	    -e RECQL_DIMS=$(DIMS) \
	    app-$(BACKEND) \
	    python -m examples.run_example $(EXAMPLE) --backend $(BACKEND) $(if $(PARAM),--param $(PARAM),); \
	else \
	  $(PYTHON) -m examples.run_example $(EXAMPLE) --backend $(BACKEND) --local $(if $(PARAM),--param $(PARAM),); \
	fi

repl: ## Launch interactive RecQL REPL for target backend
	@$(PYTHON) -m recql.cli --database "$(DATABASE)" --backend $(BACKEND) --repl

up-postgres: ## Start local PostgreSQL container
	$(COMPOSE) up -d postgres

up-mssql: ## Start local SQL Server 2025 container
	$(COMPOSE) up -d mssql

up-mongodb: ## Start local MongoDB container
	$(COMPOSE) up -d mongodb

up-mariadb: ## Start local MariaDB container
	$(COMPOSE) up -d mariadb

up-oracle: ## Start local Oracle 23ai container
	$(COMPOSE) up -d oracle

up: ## Start database container for BACKEND
	@if [ "$(BACKEND)" = "postgres" ]; then $(MAKE) up-postgres; \
	elif [ "$(BACKEND)" = "mssql" ]; then $(MAKE) up-mssql; \
	elif [ "$(BACKEND)" = "mongodb" ]; then $(MAKE) up-mongodb; \
	elif [ "$(BACKEND)" = "mariadb" ]; then $(MAKE) up-mariadb; \
	elif [ "$(BACKEND)" = "oracle" ]; then $(MAKE) up-oracle; \
	fi

down: ## Stop all database containers
	$(COMPOSE) down

reset: ## Reset volumes and containers
	$(COMPOSE) down -v
