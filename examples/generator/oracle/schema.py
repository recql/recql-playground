"""Oracle 26ai Free demo DDL — application-specific, not library."""

from __future__ import annotations

# VECTOR + Oracle Text CONTEXT. Idempotent via PL/SQL exception handling.


async def apply_demo_schema(conn, *, text_dims: int = 8, als_dims: int | None = None) -> None:
    """``conn`` is a python-oracledb async connection."""
    td = int(text_dims)
    ad = int(als_dims if als_dims is not None else td)
    stmts = [
        f"""
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE items (
      item_id VARCHAR2(128) PRIMARY KEY,
      attrs JSON,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      derived_popular_rank BINARY_DOUBLE,
      search_text CLOB
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE users (
      user_id VARCHAR2(128) PRIMARY KEY,
      attrs JSON
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE interactions (
      user_id VARCHAR2(128) NOT NULL,
      item_id VARCHAR2(128) NOT NULL,
      label BINARY_DOUBLE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      PRIMARY KEY (user_id, item_id)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        f"""
BEGIN
  DECLARE
    c NUMBER;
    cur_dims NUMBER;
  BEGIN
    SELECT COUNT(*) INTO c FROM user_tables WHERE table_name = 'TEXT_EMBEDDINGS';
    IF c > 0 THEN
      BEGIN
        SELECT TO_NUMBER(REGEXP_SUBSTR(data_type, '[0-9]+'))
          INTO cur_dims
          FROM user_tab_columns
         WHERE table_name = 'TEXT_EMBEDDINGS' AND column_name = 'EMBEDDING';
      EXCEPTION WHEN OTHERS THEN
        cur_dims := NULL;
      END;
      IF cur_dims IS NULL OR cur_dims != {td} THEN
        BEGIN EXECUTE IMMEDIATE 'DROP INDEX text_embeddings_vec_idx'; EXCEPTION WHEN OTHERS THEN NULL; END;
        EXECUTE IMMEDIATE 'DROP TABLE text_embeddings';
        c := 0;
      END IF;
    END IF;
    IF c = 0 THEN
      EXECUTE IMMEDIATE '
        CREATE TABLE text_embeddings (
          embedding_name VARCHAR2(128) NOT NULL,
          entity_id VARCHAR2(128) NOT NULL,
          embedding VECTOR({td}, FLOAT32) NOT NULL,
          PRIMARY KEY (embedding_name, entity_id)
        )';
    END IF;
  END;
END;
""",
        f"""
BEGIN
  DECLARE
    c NUMBER;
    cur_dims NUMBER;
  BEGIN
    BEGIN EXECUTE IMMEDIATE 'DROP INDEX als_embeddings_vec_idx'; EXCEPTION WHEN OTHERS THEN NULL; END;
    BEGIN EXECUTE IMMEDIATE 'DROP TABLE als_embeddings'; EXCEPTION WHEN OTHERS THEN NULL; END;

    SELECT COUNT(*) INTO c FROM user_tables WHERE table_name = 'ALS_USER_EMBEDDINGS';
    IF c > 0 THEN
      BEGIN
        SELECT TO_NUMBER(REGEXP_SUBSTR(data_type, '[0-9]+'))
          INTO cur_dims
          FROM user_tab_columns
         WHERE table_name = 'ALS_USER_EMBEDDINGS' AND column_name = 'EMBEDDING';
      EXCEPTION WHEN OTHERS THEN
        cur_dims := NULL;
      END;
      IF cur_dims IS NULL OR cur_dims != {ad} THEN
        BEGIN EXECUTE IMMEDIATE 'DROP INDEX als_user_embeddings_vec_idx'; EXCEPTION WHEN OTHERS THEN NULL; END;
        EXECUTE IMMEDIATE 'DROP TABLE als_user_embeddings';
        c := 0;
      END IF;
    END IF;
    IF c = 0 THEN
      EXECUTE IMMEDIATE '
        CREATE TABLE als_user_embeddings (
          user_id VARCHAR2(128) PRIMARY KEY,
          embedding VECTOR({ad}, FLOAT32) NOT NULL
        )';
    END IF;
  END;
END;
""",
        f"""
BEGIN
  DECLARE
    c NUMBER;
    cur_dims NUMBER;
  BEGIN
    SELECT COUNT(*) INTO c FROM user_tables WHERE table_name = 'ALS_ITEM_EMBEDDINGS';
    IF c > 0 THEN
      BEGIN
        SELECT TO_NUMBER(REGEXP_SUBSTR(data_type, '[0-9]+'))
          INTO cur_dims
          FROM user_tab_columns
         WHERE table_name = 'ALS_ITEM_EMBEDDINGS' AND column_name = 'EMBEDDING';
      EXCEPTION WHEN OTHERS THEN
        cur_dims := NULL;
      END;
      IF cur_dims IS NULL OR cur_dims != {ad} THEN
        BEGIN EXECUTE IMMEDIATE 'DROP INDEX als_item_embeddings_vec_idx'; EXCEPTION WHEN OTHERS THEN NULL; END;
        EXECUTE IMMEDIATE 'DROP TABLE als_item_embeddings';
        c := 0;
      END IF;
    END IF;
    IF c = 0 THEN
      EXECUTE IMMEDIATE '
        CREATE TABLE als_item_embeddings (
          item_id VARCHAR2(128) PRIMARY KEY,
          embedding VECTOR({ad}, FLOAT32) NOT NULL
        )';
    END IF;
  END;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE models (
      name VARCHAR2(128) NOT NULL,
      policy_type VARCHAR2(64),
      version VARCHAR2(64) DEFAULT ''v1'' NOT NULL,
      feature_spec JSON,
      blob BLOB,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      PRIMARY KEY (name, version)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE pagination_seen (
      key VARCHAR2(512) NOT NULL,
      item_id VARCHAR2(128) NOT NULL,
      expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
      PRIMARY KEY (key, item_id)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE artifact_registry (
      kind VARCHAR2(32) NOT NULL,
      name VARCHAR2(128) NOT NULL,
      version VARCHAR2(64) NOT NULL,
      dims NUMBER,
      config_hash VARCHAR2(64),
      feature_spec JSON,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      PRIMARY KEY (kind, name, version)
    )';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE INDEX items_search_ctx ON items(search_text)
    INDEXTYPE IS CTXSYS.CONTEXT
    PARAMETERS (''SYNC (ON COMMIT)'')';
EXCEPTION WHEN OTHERS THEN NULL;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE VECTOR INDEX text_embeddings_vec_idx ON text_embeddings(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95';
EXCEPTION WHEN OTHERS THEN NULL;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE VECTOR INDEX als_user_embeddings_vec_idx ON als_user_embeddings(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95';
EXCEPTION WHEN OTHERS THEN NULL;
END;
""",
        """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE VECTOR INDEX als_item_embeddings_vec_idx ON als_item_embeddings(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    DISTANCE COSINE
    WITH TARGET ACCURACY 95';
EXCEPTION WHEN OTHERS THEN NULL;
END;
""",
    ]
    for sql in stmts:
        cur = conn.cursor()
        try:
            await cur.execute(sql)
            await conn.commit()
        finally:
            cur.close()
