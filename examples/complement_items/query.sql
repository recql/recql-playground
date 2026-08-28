-- Complement / related movies for a seed title (default: Toy Story).
-- Parallel ALS + content similarity + popular pool, then LightGBM rerank.
-- Example: make example E=complement_items
SELECT score(expression='click_through_rate', input_user_id=$user_id) AS s, *
FROM retrieve(
  similarity(embedding_ref='als', encoder=precomputed_item(input_item_id=$seed_item_id),
             name='cf', limit=50),
  similarity(embedding_ref='content_embedding',
             encoder=precomputed_item(input_item_id=$seed_item_id),
             name='content', limit=50),
  column_order(columns='_derived_popular_rank ASC', name='category_pool', limit=50)
)
ORDER BY s
LIMIT 10
