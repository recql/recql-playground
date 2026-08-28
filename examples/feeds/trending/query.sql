-- Trending proxy: recent + popular blend (§2.2 merge) on MovieLens.
-- Example: make example E=feeds/trending
SELECT * FROM retrieve(
  column_order(columns='created_at DESC', limit=50, name='recent'),
  column_order(columns='_derived_popular_rank ASC', limit=50, name='popular')
) LIMIT 20
