-- Boosted reorder: interleave ALS results with Comedy titles (promo bag).
-- Uses item attrs genres (MovieLens); Postgres JSONB containment.
-- Example: make example E=boosted
SELECT score(expression='click_through_rate', input_user_id=$user_id) AS s,
       boosted(
         score=s,
         retriever=filter(
           where='e.attrs @> ''{"genres":["Comedy"]}''::jsonb',
           limit=40,
           name='comedies'
         ),
         strength=0.35
       ) AS r, *
FROM retrieve(
  similarity(
    embedding_ref='als',
    encoder=precomputed_user(input_user_id=$user_id),
    limit=100,
    name='main'
  )
)
ORDER BY r
LIMIT 20
