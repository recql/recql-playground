-- Similar movies (i2i) via ALS — default seed is Toy Story (ml-100k id 1).
-- Example: make example E=similar_items
SELECT * FROM retrieve(
  similarity(
    embedding_ref='als',
    encoder=precomputed_item(input_item_id=$item_id),
    name='similar', limit=50
  )
) LIMIT 20
