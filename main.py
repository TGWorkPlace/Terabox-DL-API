import re
import logging
import asyncio
from typing import Optional

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("terabox-api")

# ─── Constants ───────────────────────────────────────────────────────────────
BASE_URL        = "https://flowvideoplayer.com"
SEARCH_ENDPOINT = f"{BASE_URL}/telegram/bot/search/video"
HEADERS_BASE    = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; SM-M325F) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RETRIES    = 3
RETRY_DELAY    = 1.5   # seconds between retries
REQUEST_TIMEOUT = 20   # seconds

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TeraBox Stream API",
    description="Fetches stream URLs from flowvideoplayer.com",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ─── Core logic ──────────────────────────────────────────────────────────────

async def fetch_csrf_token(client: httpx.AsyncClient) -> Optional[str]:
    """GET the homepage and extract the CSRF token."""
    resp = await client.get(BASE_URL, headers=HEADERS_BASE, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', resp.text)
    if not match:
        log.warning("CSRF token not found in homepage HTML")
        return None
    return match.group(1)


async def fetch_stream_urls(terabox_url: str):
    """
    Returns (results_list, error_string).
    Retries up to MAX_RETRIES times on transient failures.
    A fresh HTTP session (with cookies) is created per attempt so that
    the CSRF token and session cookie always match.
    """
    last_error = "Unknown error"

    for attempt in range(1, MAX_RETRIES + 1):
        log.info("Attempt %d/%d for URL: %s", attempt, MAX_RETRIES, terabox_url)
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:

                # 1) Get fresh CSRF token + session cookie
                csrf = await fetch_csrf_token(client)
                if not csrf:
                    last_error = "Could not extract CSRF token"
                    raise ValueError(last_error)

                # 2) POST to search endpoint
                resp = await client.post(
                    SEARCH_ENDPOINT,
                    json={"url": terabox_url},
                    headers={
                        **HEADERS_BASE,
                        "Content-Type": "application/json",
                        "X-CSRF-TOKEN": csrf,
                        "Referer": f"{BASE_URL}/",
                        "Origin": BASE_URL,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()

                data = resp.json()

                if not data.get("status"):
                    last_error = data.get("message") or "API returned status=false"
                    log.warning("API error: %s", last_error)
                    # Don't retry on a clean API-level rejection
                    return None, last_error

                raw = data.get("response") or []
                if not raw:
                    return None, "No videos found for this URL"

                results = [
                    {
                        "file_name":     item.get("file_name"),
                        "file_size":     item.get("file_size"),
                        "download_link": item.get("fast_stream_url"),
                        "thumbnail":     item.get("thumbnail"),
                    }
                    for item in raw
                ]
                log.info("Success — %d result(s) returned", len(results))
                return results, None

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = f"Network error: {exc}"
            log.warning("Attempt %d failed (network): %s", attempt, exc)

        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code} from upstream"
            log.warning("Attempt %d failed (HTTP status): %s", attempt, last_error)

        except ValueError:
            # Already logged above; don't retry CSRF failures endlessly
            break

        except Exception as exc:
            last_error = f"Unexpected error: {exc}"
            log.exception("Attempt %d — unexpected exception", attempt)

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY * attempt)

    return None, last_error


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "TeraBox Stream API is running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


@app.get("/api", tags=["TeraBox"])
async def api(
    request: Request,
    url: str = Query(..., description="TeraBox share URL"),
):
    url = url.strip()
    if not url:
        return JSONResponse(
            status_code=400,
            content={"status": False, "message": "URL parameter is required"},
        )

    # Basic sanity check — must look like a URL
    if not url.startswith(("http://", "https://")):
        return JSONResponse(
            status_code=400,
            content={"status": False, "message": "Invalid URL format"},
        )

    log.info("Request from %s — URL: %s", request.client.host, url)

    results, error = await fetch_stream_urls(url)

    if error:
        return JSONResponse(
            status_code=502,
            content={"status": False, "message": error},
        )

    return JSONResponse(
        content={"status": True, "count": len(results), "results": results}
    )
