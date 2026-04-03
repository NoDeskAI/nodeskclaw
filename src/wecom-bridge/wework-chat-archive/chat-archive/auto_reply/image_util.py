"""Image download, intent classification, description, and pending-image tracking.

Two-layer filtering:
  Layer 1 (free): webhook metadata pre-filter (dimensions, size, direct_url)
  Layer 2 (1 LLM call): Vision LLM classifies + describes in a single request
"""
from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from config import APP_KEY, APP_SECRET, GUID, API_GATEWAY, LLM_API_URL, LLM_API_KEY, LLM_MODEL
from database import get_setting

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
DOWNLOAD_TIMEOUT = 30
LLM_VISION_TIMEOUT = 60
PENDING_IMAGE_WAIT_TIMEOUT = 15.0

MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 200
MIN_IMAGE_SIZE = 20 * 1024  # 20 KB

SKIP_TOKEN = "SKIP"

IMAGE_CLASSIFY_AND_DESCRIBE_PROMPT = """\
请先判断这张图片的类型，然后根据判断结果执行不同操作：

## 判断规则
如果图片属于以下任一类别，请直接回复"SKIP"（只回复这四个字母，不要其他内容）：
- 表情包、贴纸、GIF 动图
- 聊天截图中无明显问题的日常对话
- 风景照、自拍、食物照片等生活图片
- 广告、二维码、营销海报
- 无法识别内容的模糊图片

## 描述规则
如果图片是以下类型，请用中文描述你看到的内容：
- 软件/网页的 Bug 截图、报错界面、异常状态
- 用户操作遇到问题的截图
- 包含错误提示或异常信息的界面

描述时重点关注：
1. 界面上的错误提示、报错信息
2. 用户正在操作的功能和当前状态
3. 任何异常的 UI 元素或行为
用简洁的一段话描述，不要分析原因，只描述你看到了什么。"""


# ---------------------------------------------------------------------------
# Pending-image tracker
# ---------------------------------------------------------------------------

_pending_images: dict[tuple[str, str], asyncio.Event] = {}


def mark_image_pending(room_id: str, sender: str) -> None:
    _pending_images[(room_id, sender)] = asyncio.Event()


def mark_image_done(room_id: str, sender: str) -> None:
    event = _pending_images.pop((room_id, sender), None)
    if event:
        event.set()


async def wait_for_pending_image(room_id: str, sender: str) -> bool:
    """Block until the sender's pending image finishes (max *PENDING_IMAGE_WAIT_TIMEOUT* s).

    Returns True if a pending image was awaited and completed, False otherwise.
    """
    event = _pending_images.get((room_id, sender))
    if not event:
        return False
    try:
        await asyncio.wait_for(event.wait(), PENDING_IMAGE_WAIT_TIMEOUT)
        return True
    except asyncio.TimeoutError:
        _pending_images.pop((room_id, sender), None)
        logger.warning("[image] pending image wait timed out (%s, %s)", room_id, sender)
        return False


# ---------------------------------------------------------------------------
# Layer 1 — metadata pre-filter (zero cost)
# ---------------------------------------------------------------------------

def should_skip_by_metadata(data: dict) -> bool:
    """Return True when the image is almost certainly a sticker / emoji / icon."""
    # direct_url typically means sticker / emoji downloaded directly
    if data.get("url"):
        return True

    cdn = data.get("cdn", {})
    w = cdn.get("image_width") or data.get("width", 0)
    h = cdn.get("image_height") or data.get("height", 0)
    size = cdn.get("size", 0)

    if w and h and (w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT):
        logger.debug("[image] dimensions too small (%dx%d), skip", w, h)
        return True
    if 0 < size < MIN_IMAGE_SIZE:
        logger.debug("[image] file too small (%d B), skip", size)
        return True

    return False


# ---------------------------------------------------------------------------
# Image download (JuheBot API)
# ---------------------------------------------------------------------------

def _extract_file_id(data: dict) -> tuple[str, bool]:
    """Extract (file_id, is_hd) from webhook payload data."""
    cdn = data.get("cdn", {})
    if cdn and cdn.get("file_id"):
        return cdn["file_id"], cdn.get("is_hd", False)

    content = data.get("content", "")
    if content and content.startswith(("30", "*", "https://")):
        return content.strip(), False

    for key in ("file_id", "fileid", "fileId"):
        if data.get(key):
            return str(data[key]), False

    return "", False


def _mime_from_content_type(ct: str) -> str:
    if "png" in ct:
        return "image/png"
    if "gif" in ct:
        return "image/gif"
    if "webp" in ct:
        return "image/webp"
    return "image/jpeg"


async def fetch_image_bytes(data: dict) -> tuple[bytes, str] | None:
    """Download the image and return *(raw_bytes, mime_type)* or ``None``.

    Silently returns None on missing credentials, download failure, or oversized
    images — never raises.
    """
    if not APP_KEY or not APP_SECRET:
        logger.debug("[image] JuheBot credentials missing, skip download")
        return None

    file_id, is_hd = _extract_file_id(data)
    if not file_id:
        logger.debug("[image] no file_id in payload, skip")
        return None

    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            # Direct CDN URL (e.g. wework.qpic.cn)
            if file_id.startswith("https://wework.qpic.cn"):
                resp = await client.get(file_id)
                if resp.status_code == 200:
                    mime = _mime_from_content_type(resp.headers.get("content-type", ""))
                    return resp.content, mime
                return None

            # Determine JuheBot API path
            if file_id.startswith("30"):
                api_path = "/cloud/c2c_download"
                file_type = 1 if is_hd else 2
            elif file_id.startswith("*"):
                api_path = "/cloud/big_download"
                file_type = 2
            elif file_id.startswith("https://"):
                api_path = "/cloud/wx_download"
                file_type = 2
            else:
                api_path = "/cloud/c2c_download"
                file_type = 1 if is_hd else 2

            resp = await client.post(API_GATEWAY, json={
                "app_key": APP_KEY,
                "app_secret": APP_SECRET,
                "path": api_path,
                "data": {"guid": GUID, "file_id": file_id, "file_type": file_type},
            })
            result = resp.json()

            if result.get("error_code") != 0:
                logger.warning("[image] CDN download failed file_id=%s: %s",
                               file_id[:40], result.get("error_message"))
                return None

            download_url = (
                result.get("data", {}).get("file_url", "")
                or result.get("data", {}).get("url", "")
                or result.get("data", {}).get("download_url", "")
            )
            if not download_url:
                logger.warning("[image] no download URL for file_id=%s", file_id[:40])
                return None

            file_resp = await client.get(download_url)
            if file_resp.status_code == 200:
                mime = _mime_from_content_type(file_resp.headers.get("content-type", ""))
                return file_resp.content, mime

    except Exception as e:
        logger.error("[image] fetch_image_bytes error file_id=%s: %s", file_id[:40], e)

    return None


# ---------------------------------------------------------------------------
# Layer 2 — Vision LLM classify + describe (single call)
# ---------------------------------------------------------------------------

def _llm_cfg(key: str, fallback: str) -> str:
    return get_setting(key, fallback)


async def describe_image(data: dict) -> str | None:
    """Download an image, then ask a Vision LLM to classify and describe it.

    Returns a text description for Bug screenshots, or ``None`` for irrelevant
    images (SKIP), download failures, or LLM errors.  Never raises.
    """
    try:
        result = await fetch_image_bytes(data)
        if not result:
            return None

        img_bytes, mime = result
        if len(img_bytes) > MAX_IMAGE_BYTES:
            logger.warning("[image] image too large (%.1f MB), skip",
                           len(img_bytes) / 1024 / 1024)
            return None

        b64 = base64.b64encode(img_bytes).decode()
        data_uri = f"data:{mime};base64,{b64}"

        api_url = _llm_cfg("llm_api_url", LLM_API_URL)
        api_key = _llm_cfg("llm_api_key", LLM_API_KEY)
        model = _llm_cfg("llm_model", LLM_MODEL)

        if not api_url or not api_key:
            logger.warning("[image] LLM not configured, skip describe")
            return None

        body = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": IMAGE_CLASSIFY_AND_DESCRIBE_PROMPT},
                ],
            }],
        }

        async with httpx.AsyncClient(timeout=LLM_VISION_TIMEOUT) as client:
            resp = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"].strip()

        if reply.upper().startswith(SKIP_TOKEN):
            logger.info("[image] LLM classified as irrelevant, SKIP")
            return None

        logger.info("[image] LLM description: %s", reply[:80])
        return reply

    except Exception as e:
        logger.error("[image] describe_image error: %s", e, exc_info=True)
        return None
