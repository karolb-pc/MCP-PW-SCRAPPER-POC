# Amazon.com Product Reviews

Scrape review data from the provided Amazon.com product or reviews URL.

Return JSON with:

```json
{
  "source_url": "...",
  "items": [
    {
      "review_position": 1,
      "review_title": "...",
      "rating_text": "...",
      "rating_value": 0.0,
      "author": "...",
      "review_date_text": "...",
      "verified_purchase": true,
      "review_text": "...",
      "helpful_text": "...",
      "variant_text": "..."
    }
  ],
  "meta": {
    "mode": "direct_agent_discovery",
    "status": "ok|blocked|partial",
    "product_title": "..."
  }
}
```

Collect up to the first 20 reviews.

Review loading rules:

- Start with the visible reviews on the page.
- If fewer than 20 unique reviews are visible, look for safe visible controls that load more review rows, especially links or buttons named `Show 10 more reviews`, `Show more reviews`, `See more reviews`, `Load more reviews`, or equivalent localized text.
- Before clicking a load-more control, record the current unique review count and the identity keys of the collected reviews.
- Click the load-more control in the page UI. Prefer clicking the visible control over manually constructing or navigating to its href, because Amazon may use transient tokens.
- After clicking a load-more control, wait for the page to finish loading the next batch before extracting again.
- Do not evaluate duplicates while a spinner/progress/loading indicator is still visible. Wait until the spinner disappears and the DOM is stable, or until a clear timeout of at least 45 seconds is reached.
- After the wait, scroll slightly around the review list and re-snapshot/re-read the DOM before extracting. Some Amazon review rows render only after scroll/settle.
- If the spinner is still visible after the timeout, capture a diagnostic screenshot and return `meta.status: "partial"` with `meta.pagination_note` explaining that loading did not finish.
- Repeat until 20 unique reviews are collected or no safe load-more/pagination control remains.
- Deduplicate reviews by title, author, date, rating, and review text.
- Use normal pagination only if it is visible and safe.
- Do not mark the result as `partial` just because there is no classic `Next` pagination button. First check for lazy-load controls such as `Show 10 more reviews`.
- If a load-more control is present but fails to add unique reviews after 2 fully loaded, spinner-free attempts, return the collected rows with `meta.status: "partial"` and explain the failed control in `meta.pagination_note`.
- In `meta`, include `collected_count`, `target_count`, `load_more_clicks`, `load_more_timeouts`, and `pagination_note`.

Do not log in unless the host command explicitly enables credentials. Do not vote, sort in a way that changes account state, or bypass access controls.
