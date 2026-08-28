-- Diversity + exploration reorder on ALS recommendations for user 55.
-- Example: make example E=filter_bubbles
SELECT score(expression='click_through_rate', input_user_id=$user_id) AS s,
       diversity(score=s, strength=0.3) AS d,
       exploration(score=s, strength=0.2) AS e, *
FROM retrieve(
  similarity(embedding_ref='als', encoder=precomputed_user(input_user_id=$user_id),
             limit=100)
)
ORDER BY e
LIMIT 20
