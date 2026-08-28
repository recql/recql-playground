-- Semantic (vector) search over MovieLens content embeddings.
-- Example: make example E=search/semantic
--   query_text ≈ "sci-fi space adventure" | "animated children's comedy"
SELECT *
FROM retrieve(
  text_search(
    query=$query_text, mode='vector',
    text_embedding_ref='content_embedding', limit=20, name='vector'
  )
)
LIMIT 20
