-- For-you feed: ALS u2i for MovieLens user 55 + popular cold-start, exclude seen.
-- Ranks by ALS similarity (not raw popularity). Re-seed after model changes.
-- Example: make example E=feeds/for_you
SELECT score(expression='retrieval.get_score("user_vector", 0)') AS als_score, *
FROM retrieve(
  similarity(embedding_ref='als', encoder=precomputed_user(input_user_id=$user_id),
             name='user_vector', limit=50),
  column_order(columns='_derived_popular_rank ASC', name='cold_start', limit=50)
)
WHERE prebuilt('exclude_seen', input_user_id=$user_id)
ORDER BY als_score
LIMIT 20
