import os
import logging
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from TeraboxDL import TeraboxDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Terabox Downloader API",
    description="API to fetch Terabox file info: download link, thumbnail, name, size, etc.",
    version="1.0.0",
)

TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "")


def get_terabox_client() -> TeraboxDL:
    if not TERABOX_COOKIE:
        raise HTTPException(
            status_code=500,
            detail="TERABOX_COOKIE environment variable is not set.",
        )
    return TeraboxDL(TERABOX_COOKIE)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Terabox Downloader API is running.",
        "usage": "/api?url=<terabox_share_link>",
    }


@app.get("/api")
async def get_file_info(url: str = Query(..., description="Terabox share URL")):
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' query parameter.")

    logger.info(f"Fetching info for: {url}")

    try:
        client = get_terabox_client()
        file_info = client.get_file_info(url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    if "error" in file_info:
        raise HTTPException(status_code=400, detail=file_info["error"])

    response = {
        "success": True,
        "file_name": file_info.get("file_name"),
        "file_size": file_info.get("file_size"),
        "file_size_bytes": file_info.get("sizebytes"),
        "download_link": file_info.get("download_link"),
        "thumbnail": file_info.get("thumbnail"),
    }

    logger.info(f"Success: {response['file_name']} ({response['file_size']})")
    return JSONResponse(content=response)


@app.get("/health")
async def health():
    return {"status": "healthy"}
