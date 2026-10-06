"""Telegram sender — posts briefs and status messages to the configured channel.

Uses Markdown (v1) parse mode because the brief format in docs/lead-template.md
uses *bold*, [text](url), bullet lists, which Telegram's loosest Markdown
supports with the fewest escape rules.
"""
from __future__ import annotations
import logging
import time

import httpx

from scripts.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

log = logging.getLogger(__name__)

TG_MAX_LEN = 4000  # leave headroom under hard 4096 limit


def send_text(text: str) -> None:
    """Send a plain status/greeting message (short, single chunk expected)."""
    send_brief(text)


def send_brief(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID not set")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chunk in _split(text, TG_MAX_LEN):
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        with httpx.Client(timeout=30) as c:
            r = c.post(url, json=payload)
            if r.status_code >= 400:
                log.error("telegram error %s: %s", r.status_code, r.text)
                payload.pop("parse_mode", None)
                r = c.post(url, json=payload)
                r.raise_for_status()
        time.sleep(1)


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > limit:
            out.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        out.append(cur)
    return out
