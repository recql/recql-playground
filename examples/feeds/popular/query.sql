-- Most-rated MovieLens titles (popular_rank ASC = most popular first).
-- Example: make example E=feeds/popular
-- Expect Star Wars (50), Contact (258), Fargo (100), … near the top on full ml-100k.
SELECT * FROM retrieve(
  column_order(columns='_derived_popular_rank ASC', limit=50, name='popular')
) LIMIT 20
