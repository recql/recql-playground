-- Personalized hybrid search: text + ALS taste for MovieLens user 55.
-- Example: make example E=search/personalized
SELECT *
FROM retrieve(
  text_search(query=$query_text, mode='vector',
              text_embedding_ref='content_embedding', limit=50, name='vector_search'),
  text_search(query=$query_text, mode='lexical', fuzziness=2, limit=50, name='lexical_search'),
  similarity(embedding_ref='als', encoder=precomputed_user(input_user_id=$user_id),
             name='user_vector', limit=50)
)
ORDER BY score(
  expression='0.4 * retrieval.get_score("vector_search", 0) + 0.3 * retrieval.get_score("lexical_search", 0) + 0.3 * retrieval.get_score("user_vector", 0)'
)
LIMIT 20
