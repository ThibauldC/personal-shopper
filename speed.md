## Speed issue summary

The strict vegetarian/vegan filtering now works, but reaching 8 valid recipes is slow because the pipeline must fetch many recipe detail pages before finding enough accepted items.

### Observed behavior

- Detail requests to Delhaize are often slow (roughly 10-20 seconds per recipe detail URL).
- Many candidate recipes are rejected by strict rules (meat/fish/seafood/dessert/non-main-course), so acceptance rate is low.
- Even after adding sitemap-based candidate expansion, the fetch loop can still process dozens of detail pages before reaching the target count.
- End-to-end `uv run python main.py` can exceed 15 minutes in current network/content conditions.

### Why this happens

1. Candidate quality is mixed: listing pages and sitemap include many non-target recipes.
2. Filtering happens after detail fetch: the system needs full page metadata before deciding.
3. Requests are currently sequential: each slow response blocks progress.

### Recommended optimizations

1. Add bounded concurrency for detail fetches (for example 4-8 workers) while preserving deterministic stop-at-8 behavior.
2. Improve pre-filtering of sitemap candidates from URL slug terms to reduce low-probability candidates.
3. Prioritize likely-good sources first, then fall back to broader sitemap pools.
4. Add a time budget / fail-safe to return the best available set when upstream is slow.

### Current status

- Functional correctness: strict filtering is enforced.
- Performance: still network-bound and candidate-quality-bound; optimization work remains.
