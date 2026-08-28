-- Lexical search over MovieLens titles / genre descriptions.
-- Example: make example E=search/lexical
--   query_text ≈ "Star Wars" | "Toy Story" | "Hitchcock"
SELECT *
FROM retrieve(
  text_search(query=$query_text, mode='lexical', fuzziness=2, limit=20, name='lexical')
)
LIMIT 20
