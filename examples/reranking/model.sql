-- LightGBM rerank over fixed MovieLens candidates.
-- Defaults: Toy Story (1), Four Rooms (3), Copycat (5), Shanghai Triad (6).
-- Example: make example E=reranking/model
SELECT score(expression='click_through_rate', input_user_id=$user_id) AS ctr, *
FROM retrieve(ids(ids=$candidate_item_ids, name='candidates'))
ORDER BY ctr
LIMIT 20
