# WebStalker

A local-only web app for monitoring website changes. It periodically fetches
your URLs, stores each version as content-addressed blobs in SQLite, and shows
GitHub-style diffs whenever a page changes.

- Backend: **FastAPI** (Python 3.11+) with **APScheduler** for periodic jobs.
- UI: server-rendered **Jinja2** templates with a small CSS file. No Node build.
- Storage: **SQLite** + a content-addressed blob directory on disk.
- Scanning: **httpx** for raw HTML, BeautifulSoup for asset extraction, optional
  **Playwright** for JavaScript-rendered pages.

## Quick start (local)

```bash
git clone <this repo>
cd webstalker

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn webstalker.main:app --reload
```

Open <http://127.0.0.1:8000>.

The first time the app runs it creates `data/webstalker.db` and `data/blobs/`
automatically — there is no separate "init database" step.

### Optional: Playwright for JS-rendered pages

```bash
pip install playwright
playwright install chromium
```

Once installed, you can pick **Browser-rendered (Playwright)** as the scan mode
on a website. If Playwright isn't available, those scans log a clear error.

## Quick start (Docker)

```bash
docker compose up --build
```

The app binds to `127.0.0.1:8000` on the host and persists data to `./data`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests stub out HTTP fetching, so no network access is required.

## Configuration

All settings have sensible defaults and can be overridden via env vars (see
`.env.example`):

| Variable | Default | Description |
| --- | --- | --- |
| `WEBSTALKER_DATA_DIR` | `data` | Directory for SQLite + blob storage |
| `WEBSTALKER_BIND_HOST` | `127.0.0.1` | uvicorn host |
| `WEBSTALKER_BIND_PORT` | `8000` | uvicorn port |
| `WEBSTALKER_REQUEST_TIMEOUT_SECONDS` | `30` | Per-request fetch timeout |
| `WEBSTALKER_ASSET_TIMEOUT_SECONDS` | `15` | Asset fetch timeout |
| `WEBSTALKER_MAX_ASSET_SIZE_BYTES` | `5242880` | Max bytes per asset |
| `WEBSTALKER_MAX_ASSETS_PER_PAGE` | `50` | Cap on assets per scan |
| `WEBSTALKER_USER_AGENT` | `WebStalker/0.1` | Outgoing User-Agent |
| `WEBSTALKER_ENABLE_SCHEDULER` | `true` | Disable to run without background scans |

## How local version storage works

WebStalker uses a Git-inspired layout to keep storage tight:

- Every file content is hashed with **SHA-256** and stored once at
  `data/blobs/<aa>/<bbcc...>`. Identical bytes are never duplicated.
- A **version** row records: website ID, version number, parent version ID,
  timestamps, the HTTP status, and a `normalized_hash` (the hash used for
  change detection after applying ignore rules).
- A **snapshot entry** ties one version to one stored blob, with a path
  (e.g. `index.html`, `assets/style.css`), the source URL, and content type.
- A **verification log** is written for every scan attempt — including
  unchanged scans and errors. Each log links the previous version it compared
  against and (if applicable) the new version it created.

When you download a version's ZIP, WebStalker reassembles the snapshot tree
from blobs and includes a `metadata.json` with the version metadata.

### Change detection

Before hashing, the fetched HTML is **normalized** according to the website's
ignore rules:

- **Ignore whitespace**: collapse runs of whitespace before comparing.
- **Ignore CSS selectors**: a list of selectors (one per line) whose matching
  elements are removed before hashing — useful for live-clock widgets,
  per-request CSRF tokens, etc.
- **Ignore URL patterns**: a list of regular expressions that are stripped from
  the page text — useful for cache-busted asset URLs.
- **Ignore timestamps**: common timestamp shapes (ISO-8601, "2024-05-04",
  "12:34", "Thu, 04 May 2024…", unix epochs) are masked.

If the normalized hash matches the latest stored version, no new version is
created — just a log entry with `result=unchanged`.

## REST API

The HTML UI is built on top of a small REST API:

| Endpoint | Method | Description |
| --- | --- | --- |
| `/api/websites` | GET | List all websites |
| `/api/websites` | POST | Create a website (triggers an initial scan) |
| `/api/websites/{id}` | GET / PUT / DELETE | CRUD for one website |
| `/api/websites/{id}/scan` | POST | Manually scan one website |
| `/api/websites/scan-all` | POST | Manually scan all enabled websites |
| `/api/websites/{id}/versions` | GET | List versions newest-first |
| `/api/websites/{id}/logs` | GET | List verification logs newest-first |
| `/api/versions/{id}` | GET | Version metadata + snapshot entries |
| `/api/versions/{id}/diff` | GET | File-by-file diff against parent version |
| `/api/versions/{id}/download` | GET | Download the version as a ZIP |

## Project layout

```
webstalker/
├── webstalker/
│   ├── main.py              FastAPI app + lifespan + routes wiring
│   ├── config.py            Settings + paths
│   ├── db.py                SQLAlchemy engine + session helpers
│   ├── models.py            ORM models (websites, versions, blobs, logs, ...)
│   ├── schemas.py           Pydantic request/response schemas
│   ├── storage.py           Content-addressed blob storage
│   ├── normalize.py         HTML normalization & ignore rules
│   ├── interval.py          Verification-interval helpers
│   ├── scanner.py           Fetch, compare, version creation, locking
│   ├── scheduler.py         APScheduler integration
│   ├── diff.py              Unified-diff generation
│   ├── api/                 REST endpoints
│   ├── web/                 Server-rendered HTML page routes
│   ├── templates/           Jinja2 templates
│   └── static/              CSS
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Reliability notes

- **Concurrent scans of the same website are prevented** with a per-website
  in-process lock; if a scan is still running, a new request logs an error
  ("scan already running, skipped") and returns.
- **HTTP errors and timeouts are logged**; the website's `last_status` becomes
  `error` and the scheduled cadence continues.
- **URLs are validated** against `https?://` and stored bounded to 2000 chars.
- **Blob filenames are derived strictly from sha256 hex** — no user input
  reaches the filesystem path.
- **All timestamps are stored as timezone-aware UTC**.

## Limitations / extension points

- Concurrent scans are coordinated **in-process**. Running multiple worker
  processes against the same SQLite file would need a DB-backed lock.
- `git`-style content-addressed storage is on the file blob layer only; the
  version graph is linear (no branches or merges).
- Asset capture is opt-in (HTML + same-origin assets) and intentionally
  conservative (`max_assets_per_page`, `max_asset_size_bytes`). Everything
  else (3rd-party CDNs, fonts, video) is skipped.
