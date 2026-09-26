# HW4 Metrics - s3319 (Domain 7: Community sports league fixtures)

## Part 3 - N+1 measurement (naive vs fixed list endpoint)

Setup: 5,000 fixtures and 200 teams seeded with SEED 3319. FastAPI on localhost:8619, MySQL 8.0.30,
MacBook Pro (Apple M2, 8 GB). 30 measured requests per case after 3 warm up requests, naive and fixed
interleaved. Latency is end to end client time. SQL statements are counted per request with a
SQLAlchemy before_cursor_execute hook (includes 1 session lookup).
Raw data: raw/n1_requests.csv (180 rows), summary: raw/n1_summary.json (run 2026-09-25T16:49:24).

| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 12 | 9.90 | 10.53 | 10.75 |
| 10 | fixed | 2 | 4.56 | 5.17 | 5.49 |
| 50 | naive | 52 | 32.44 | 40.75 | 49.71 |
| 50 | fixed | 2 | 6.24 | 7.15 | 7.49 |
| 200 | naive | 202 | 111.56 | 133.10 | 139.17 |
| 200 | fixed | 2 | 11.25 | 11.98 | 12.22 |

### Speed-up (naive p50 / fixed p50)

| Page size | Speed-up |
|---|---|
| 10 | 2.17x |
| 50 | 5.20x |
| 200 | 9.92x |

### Index (EXPLAIN before / after)

| Query | Before | After |
|---|---|---|
| fixtures WHERE venue = 'San Jose Stadium' | type ALL, key NULL, rows 4890 | type ref, key idx_fixtures_venue, rows 35 |