-- Personalized interaction pooling feed: pools item embeddings of user's recent interactions.
-- Example: make example E=feeds/interaction_pooling
SELECT *
FROM similarity(
  embedding='als',
  encoder=interaction_pooling(input_user_id=$user_id, pooling_function='mean', truncate_interactions=10),
  limit=50
)
WHERE prebuilt(filter_ref='exclude_seen', input_user_id=$user_id)
LIMIT 20
