# Amazon.com Search: MacBooks CSV

Scrape MacBook search results from the provided Amazon.com search results URL.

Write the final output as RFC 4180-style CSV, not JSON. The first row must be this exact header:

```csv
position,title,brand_or_series,price_text,price_value,currency,rating_text,rating_value,reviews_count,availability_text,delivery_text,prime_badge,sponsored,product_url,status,blocked_reason
```

Rows:

- Collect up to the first 24 organic-looking product result cards visible in the search listing.
- Keep sponsored products but set `sponsored` to `true` when a sponsored label is visible; otherwise `false`.
- Set `prime_badge` to `true` when Prime is visibly indicated; otherwise `false`.
- Use `USD` for `currency` when a dollar price is visible.
- Normalize `price_value`, `rating_value`, and `reviews_count` only when safe; otherwise leave the numeric cell empty.
- Preserve useful raw text in `price_text`, `rating_text`, `availability_text`, and `delivery_text`.
- Use absolute URLs in `product_url` when possible.
- Set `status` to `ok` for normal product rows.
- Set `blocked_reason` empty for normal product rows.

CSV rules:

- Do not wrap the CSV in Markdown fences.
- Escape commas, quotes, and newlines according to normal CSV rules.
- If Amazon shows CAPTCHA, bot challenge, login wall, unavailable page, or repeated navigation failure, do not bypass it. Write only the header and one blocker row with `status` set to `blocked`, `blocked_reason` explaining the blocker, and product fields left empty where unavailable.
