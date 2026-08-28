-- ColBERT-style rerank over hybrid MovieLens retrieval.
-- Example: make example E=reranking/colbert
SELECT score(expression='colbert_v2(item, $query_text)') AS s, *
FROM retrieve(
  text_search(query=$query_text, mode='vector',
              text_embedding_ref='content_embedding', limit=50, name='vector_search'),
  text_search(query=$query_text, mode='lexical', limit=50, name='lexical_search')
)
ORDER BY s
LIMIT 20
