-- Cross-Database Federated Demo Query
-- Retrieves candidates across PostgreSQL, Oracle 23ai, and MariaDB concurrently:
--   1. Oracle 23ai: AI Vector Search semantic ANN (content_embedding)
--   2. PostgreSQL: Collaborative filtering (ALS user factors)
--   3. MariaDB: FullText BM25 lexical keyword matching
-- Postfilter:
--   4. PostgreSQL: Interaction history (prebuilt exclude_seen filter)
-- Scoring:
--   5. PostgreSQL: LightGBM ranker model evaluation
SELECT *
FROM retrieve(
  text_search(query=$query_text, mode=vector(text_embedding_ref='content_embedding'), limit=20),
  similarity(embedding_ref='als', encoder=precomputed_user(input_user_id=$user_id), limit=20),
  text_search(query=$query_text, mode='lexical', limit=20)
)
WHERE prebuilt(filter_ref='exclude_seen', input_user_id=$user_id)
ORDER BY score(model='click_through_rate') DESC
LIMIT 10;
