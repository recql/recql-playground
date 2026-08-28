-- Cross-encoder rerank of MovieLens candidates for a text query.
-- Example: make example E=reranking/cross_encoder
SELECT score(expression='cross_encoder(item, $query_text)') AS s, *
FROM retrieve(ids(ids=$candidate_item_ids, name='candidates'))
ORDER BY s
LIMIT 20
