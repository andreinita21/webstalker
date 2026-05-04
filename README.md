<div align="center">

# WebStalker

**Watch any website for changes. See exactly what changed, when, and how, with a GitHub-style diff.**

A small, local-only web app for monitoring website changes.
Runs on your own machine. Stores everything in a SQLite database.
Nothing is sent to a third party.

[Quick start](#quick-start) ·
[How it works](#how-it-works) ·
[Features](#features) ·
[FAQ](#faq) ·
[Contributing](#contributing)

</div>

---

## What is WebStalker?

WebStalker is a website-change tracker for people who need to know,
**precisely**, when a page they care about updates. You give it a URL and a
schedule. It fetches the page in the background, stores every changed version
locally, and shows you a diff like the one you'd see in a GitHub pull request.

Useful for:

- Watching competitors' marketing pages, pricing tables, or job listings.
- Detecting silent updates to terms of service, privacy policies, status pages.
- Catching defacement, drift, or unintended changes on your own sites.
- Archiving subpages of a site over time, HTTrack-style, with a built-in diff.

It's intentionally a **local tool**. There is no cloud, no account, no
multi-tenant database. Open it in your browser at `http://127.0.0.1:8000`.

## Quick start

The fastest way is the bundled launcher script. From a terminal:

```bash
git clone https://github.com/andreinita21/webstalker.git
cd webstalker
./run.sh
```

`run.sh` will:

1. Find a compatible Python (3.11, 3.12, or 3.13).
2. Create a private virtual environment in `.venv/`.
3. Install the dependencies (only the first time, or when they change).
4. Start the app on `http://127.0.0.1:8000`.

Open that URL in your browser. Press <kbd>Ctrl</kbd>+<kbd>C</kbd> in the
terminal to stop. Re-run `./run.sh` any time, it's safe to run repeatedly.

> **Don't have Python installed?**
> - **macOS**: `brew install python@3.12`
>   ([install Homebrew](https://brew.sh) first)
> - **Ubuntu / Debian**: `sudo apt install python3-venv python3-pip`
> - **Windows**: install [Python 3.12 from python.org](https://www.python.org/downloads/),
>   then run `.\run.sh` from Git Bash, or use the Docker option below.

### Run with Docker (no Python needed)

If you have [Docker](https://docs.docker.com/get-docker/) installed:

```bash
git clone https://github.com/andreinita21/webstalker.git
cd webstalker
docker compose up --build
```

Then open `http://127.0.0.1:8000`. Your data is persisted in `./data` on the host.

## Your first scan, in 30 seconds

1. Open `http://127.0.0.1:8000`.
2. Click **Add website**.
3. Give it a name and a URL. The defaults (every 1 hour, raw HTML) are fine.
4. Click **Add website** at the bottom of the form.

WebStalker fetches the page immediately and saves it as **version 1**. From
then on it re-checks at the interval you chose. Each time the page **really**
changes, a new version is created and the live activity feed shows what
happened. You can click any version to see a side-by-side, GitHub-style diff,
or download the saved snapshot as a ZIP.

## Features

- **GitHub-style diffs** with line numbers, added/removed coloring, and
  collapsible per-file sections. Big diffs are truncated cleanly with a
  pointer to the ZIP download.
- **Smart change detection.** WebStalker normalizes the HTML before comparing
  so trivial differences don't create new versions. You control which
  differences count: ignore whitespace, ignore timestamps, ignore selected
  CSS elements (`#cookie-banner`, `.live-clock`), or ignore arbitrary URL
  patterns.
- **Four scan modes:**
  | Mode | What it captures |
  | --- | --- |
  | **Raw HTML** | Just the page returned by the server. Fastest. |
  | **HTML + assets** | The page plus same-origin CSS, JS, and images. |
  | **Crawl subpages (HTTrack-style)** | Recursively follows same-origin links from the start URL up to your chosen depth and page cap, storing every reached HTML page. The diff covers the whole site. |
  | **Browser-rendered (Playwright)** | Fully renders JavaScript-driven pages in headless Chromium. Optional install. |
- **Live activity feed** powered by Server-Sent Events. Every scan, scheduled
  or manual, streams to your browser in real time, with status badges that
  update without a page refresh.
- **Background scans never get stuck on you.** Close the tab, walk away, the
  scheduler keeps running. When you return, the recent activity replays and
  the full history lives in the Logs tab.
- **Content-addressed storage.** Every captured byte is hashed (SHA-256) and
  stored once. Two pages with identical content share one blob. Old versions
  cost nothing to keep.
- **Manual or scheduled.** Hit **Scan now** on any page, or **Scan all now**
  on the dashboard, whenever you want a check off-schedule.
- **Snapshot ZIP download.** Every version exports as a self-contained ZIP
  with the original HTML, captured assets, and a `metadata.json`.
- **REST API** for scripting. The whole UI is built on top of a small,
  well-defined JSON API (see [API reference](#api-reference)).
- **Keyboard-friendly, light/dark theme**, follows your system preference.
- **No telemetry, no analytics, no external services.** Everything runs in
  your local Python process and writes to your local `data/` directory.

## How it works

```
                ┌─────────────────────────────┐
                │   Browser  (HTML + SSE)     │
                └────────────────┬────────────┘
                                 │ http://127.0.0.1:8000
                ┌────────────────┴────────────┐
                │  FastAPI app                │
                │  ├── Jinja templates        │
                │  ├── REST API               │
                │  └── SSE event stream       │
                └────────────────┬────────────┘
                                 │
                ┌────────────────┴────────────┐
                │  APScheduler (background)   │
                │  ├── runs scans on a clock  │
                │  └── runs ad-hoc manual scans│
                └────────────────┬────────────┘
                                 │
                ┌────────────────┴────────────┐
                │  data/                      │
                │  ├── webstalker.db (SQLite) │
                │  └── blobs/                 │
                │       └── aa/bbcc...        │
                └─────────────────────────────┘
```

Each scan does roughly this:

1. Fetch the page (one URL, several URLs for the assets mode, or many for
   crawl mode).
2. Normalize the HTML according to the website's ignore rules and hash the
   result with SHA-256.
3. Compare the hash with the latest stored version.
4. If unchanged: append a log entry, no new version.
5. If changed: store the new bytes (only the parts not already stored) and
   write a new version with a parent pointer to the previous one.

## Configuration

All settings have sensible defaults. Override them with environment
variables (see `.env.example`):

| Variable | Default | What it does |
| --- | --- | --- |
| `WEBSTALKER_DATA_DIR` | `data` | Where the SQLite file and blobs live |
| `WEBSTALKER_BIND_HOST` | `127.0.0.1` | Host the server binds to |
| `WEBSTALKER_BIND_PORT` | `8000` | Port the server binds to |
| `WEBSTALKER_REQUEST_TIMEOUT_SECONDS` | `30` | Per-request fetch timeout |
| `WEBSTALKER_ASSET_TIMEOUT_SECONDS` | `15` | Asset fetch timeout |
| `WEBSTALKER_MAX_ASSET_SIZE_BYTES` | `5242880` | Per-file size cap (5 MB) |
| `WEBSTALKER_MAX_ASSETS_PER_PAGE` | `50` | Cap on assets per scan |
| `WEBSTALKER_USER_AGENT` | `WebStalker/0.1` | Outgoing User-Agent header |
| `WEBSTALKER_ENABLE_SCHEDULER` | `true` | Set to `false` to run without the background scheduler |

You can put these in a `.env` file at the project root. The app picks them
up automatically.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

The tests run fully offline. They use `httpx.MockTransport` to fake HTTP
responses, so no network access is required.

## API reference

The HTML UI is a thin layer over a clean REST API.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/websites` | List all websites |
| `POST` | `/api/websites` | Add a website (triggers an initial scan) |
| `GET` | `/api/websites/{id}` | One website |
| `PUT` | `/api/websites/{id}` | Edit settings |
| `DELETE` | `/api/websites/{id}` | Delete a website and all its versions |
| `POST` | `/api/websites/{id}/scan` | Manually scan one website |
| `POST` | `/api/websites/scan-all` | Manually scan every enabled website |
| `GET` | `/api/websites/{id}/versions` | List versions, newest first |
| `GET` | `/api/websites/{id}/logs` | Verification log entries, newest first |
| `GET` | `/api/versions/{id}` | Version metadata + snapshot entries |
| `GET` | `/api/versions/{id}/diff` | File-by-file diff against the parent |
| `GET` | `/api/versions/{id}/download` | ZIP download |
| `GET` | `/api/events` | Server-Sent Events stream of scan events |
| `GET` | `/api/events/recent` | JSON snapshot of recent scan events |

OpenAPI docs are available at `http://127.0.0.1:8000/docs` while the app is
running.

## FAQ

**Does WebStalker send my data anywhere?**
No. It runs on your machine, binds by default to `127.0.0.1` (only your
laptop can reach it), writes to `./data/`, and has no telemetry. The only
network calls are the ones it makes to the websites you ask it to watch.

**Can I host it for a small team?**
You can, but it ships with no authentication on purpose. If you expose it
beyond `127.0.0.1`, put it behind a reverse proxy with auth, or run it
inside a private network you trust.

**How big can `data/` get?**
Each version stores only the bytes that actually changed since the previous
version (content-addressed blobs), so a site that updates rarely uses very
little space. A noisy site with many small changes can grow faster, in
which case raise the ignore rules or shorten the retention later.

**Can I delete an old version?**
Right now versions are immutable; deleting a website removes all of its
versions and the blobs that aren't shared with other websites.

**Why can't I scan a JavaScript-heavy page in raw mode?**
Raw and assets modes only fetch what the server returns. If the page is
client-side rendered, switch the website's scan mode to **Browser-rendered
(Playwright)** and install Playwright once:

```bash
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
```

**How does the crawl mode (HTTrack-style) decide what to follow?**
It does a breadth-first walk starting from the URL you provide. It only
follows links to the **same scheme + host**. It stops at the depth and
page-cap you set on the website (defaults: 25 pages, depth 2). Non-HTML
responses are skipped. Each reached page is stored as a separate file in
the snapshot, so the diff naturally becomes a multi-file diff.

## Project layout

```
webstalker/
├── webstalker/             Application package
│   ├── main.py             FastAPI app, lifespan, route wiring
│   ├── db.py               SQLAlchemy engine + lightweight migrations
│   ├── models.py           ORM models (websites, versions, blobs, logs, ...)
│   ├── schemas.py          Pydantic request/response schemas
│   ├── storage.py          Content-addressed blob storage
│   ├── normalize.py        HTML normalization & ignore rules
│   ├── interval.py         Verification-interval helpers
│   ├── scanner.py          Fetch, crawl, compare, version creation
│   ├── scheduler.py        APScheduler integration
│   ├── events.py           Pub/sub for the live activity stream
│   ├── diff.py             Unified-diff generation
│   ├── api/                REST endpoints
│   ├── web/                Server-rendered HTML page routes
│   ├── templates/          Jinja2 templates
│   └── static/             CSS + a small vanilla-JS file
├── tests/                  pytest suite (offline, deterministic)
├── run.sh                  One-shot launcher
├── Dockerfile / docker-compose.yml
├── PRODUCT.md              Product strategy and design principles
├── DESIGN.md               Visual system, tokens, components
└── README.md               (this file)
```

## Contributing

Bug reports, feature ideas, and pull requests are welcome at
[github.com/andreinita21/webstalker](https://github.com/andreinita21/webstalker).
The codebase is intentionally small and easy to read.

Before opening a PR, please run the test suite:

```bash
.venv/bin/pytest
```

## License

This project is provided as-is for personal and internal use. See the
repository for license details.
