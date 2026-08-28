-- Similar movies within a MovieLens genre facet (default: Animation around Toy Story).
-- Example: make example E=faceted_filtering
SELECT * FROM retrieve(
  similarity(
    embedding_ref='content_embedding',
    encoder=precomputed_item(input_item_id=$reference_item_id),
    name='similar', limit=200
  )
)
WHERE array_has(genres, $genre)
ORDER BY score(expression='click_through_rate', input_user_id=$user_id)
LIMIT 20
