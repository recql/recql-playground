-- Paginated popular MovieLens feed.
-- Run twice with the same --pagination-key to exclude the prior page.
-- Example: make example E=pagination PAGINATION_KEY=ml-pop-1
SELECT * FROM retrieve(
  column_order(columns='_derived_popular_rank ASC', limit=50, name='popular')
) LIMIT 5
