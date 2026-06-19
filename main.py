# main.py
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import requests
import re

app = FastAPI()

def get_stream_url(terabox_url: str):
    session = requests.Session()

    home = session.get("https://flowvideoplayer.com/", headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-M325F) AppleWebKit/537.36"
    })

    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', home.text)
    if not match:
        return None, "Could not extract CSRF token"

    csrf_token = match.group(1)

    response = session.post(
        "https://flowvideoplayer.com/telegram/bot/search/video",
        json={"url": terabox_url},
        headers={
            "Content-Type": "application/json",
            "X-CSRF-TOKEN": csrf_token,
            "Referer": "https://flowvideoplayer.com/",
            "Origin": "https://flowvideoplayer.com",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-M325F) AppleWebKit/537.36",
        }
    )

    data = response.json()

    if not data.get("status"):
        return None, data.get("message", "Failed to fetch video")

    results = []
    for item in data.get("response", []):
        results.append({
            "file_name": item.get("file_name"),
            "file_size": item.get("file_size"),
            "download_link": item.get("fast_stream_url"),
            "thumbnail": item.get("thumbnail"),
        })

    return results, None


@app.get("/api")
async def api(url: str = Query(..., description="TeraBox URL")):
    if not url:
        return JSONResponse(status_code=400, content={"status": False, "message": "URL is required"})

    results, error = get_stream_url(url)

    if error:
        return JSONResponse(status_code=500, content={"status": False, "message": error})

    return JSONResponse(content={
        "status": True,
        "results": results
    })


@app.get("/")
async def root():
    return {"status": "ok", "message": "TeraBox API is running"}
