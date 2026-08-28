-- Newest MovieLens releases (by release / created_at).
-- Example: make example E=feeds/new
SELECT * FROM retrieve(
  column_order(columns='created_at DESC', limit=50, name='new')
) LIMIT 20
