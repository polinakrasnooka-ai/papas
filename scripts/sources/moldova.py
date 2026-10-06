"""Moldova procurement sweep.

Moldova is not in TED (not an EU member) but is the closest buyer market
to our Kodyma shipping base (~130 km to Lafarge Rezina). This module runs
one Claude call per daily cron that uses web_search + web_fetch to crawl
the Moldovan procurement systems and return any new limestone tenders as
Notice objects, deduped by the same SQLite state table as TED notices.

Why not a real HTTP client? MTender uses the OpenProcurement API, which
has a stable JSON schema but requires per-category filtering; achizitii.md
scrapes it with its own UI; tender.gov.md adds a third surface. Rather
than ship three fragile scrapers for an MVP, we let Claude navigate.
Later: swap this for a direct api.openprocurement.org client.
"""
from __future__ import annotations
import hashlib
import logging
import re

from anthropic import Anthropic

from scripts.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from scripts.sources.ted import Notice

log = logging.getLogger(__name__)

MOLDOVA_SOURCES = [
    "mtender.gov.md",
    "achizitii.md",
    "tender.gov.md",
]

PROMPT = (
    "Задача: найди активные тендеры (объявленные/открытые/с дедлайном в "
    "ближайшие 60 дней) на известняк в Молдове. Используй только эти сайты:\n"
    "- mtender.gov.md\n- achizitii.md\n- tender.gov.md\n\n"
    "Поиск по ключевым словам (RO + RU): calcar, piatră de calcar, "
    "carbonat de calciu, var, известняк, карбонат кальция, щебень известняковый, "
    "limestone, calcium carbonate. CPV 14212*, 44921*.\n\n"
    "Для каждого найденного активного тендера верни ОДНУ строку "
    "строго в формате (разделитель — вертикальная черта):\n\n"
    "MD|<buyer name>|<title in RO or RU>|<URL to the tender page>|<deadline YYYY-MM-DD or ->\n\n"
    "Если за этот прогон ничего не найдено — верни одно слово: NONE\n"
    "Больше ничего не пиши."
)


def sweep_moldova() -> list[Notice]:
    """Return Notice objects for Moldovan tenders. Empty list on no results / errors."""
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY unset; skipping Moldova sweep")
        return []

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 5,
            "allowed_domains": MOLDOVA_SOURCES + ["google.com"],
        },
        {
            "type": "web_fetch_20260209",
            "name": "web_fetch",
            "max_uses": 8,
        },
    ]

    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1500,
            tools=tools,
            messages=[{"role": "user", "content": PROMPT}],
        )
    except Exception as e:
        log.exception("Moldova sweep API call failed: %s", e)
        return []

    text = "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    ).strip()

    if not text or text.upper() == "NONE":
        log.info("Moldova sweep: no new tenders")
        return []

    notices: list[Notice] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not line.startswith("MD|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            log.warning("malformed Moldova line: %s", line[:120])
            continue
        buyer = parts[1]
        title = parts[2]
        url = parts[3]
        deadline = parts[4] if len(parts) >= 5 and parts[4] not in ("", "-") else None
        if not _looks_like_url(url):
            log.warning("bad URL in Moldova line: %s", line[:120])
            continue
        pseudo_id = "md:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        notices.append(Notice(
            id=pseudo_id,
            title=title,
            buyer=buyer,
            country="MDA",
            cpv=[],
            publication_date="",
            deadline=deadline,
            notice_type="MD-tender",
            url=url,
        ))

    log.info("Moldova sweep returned %d tender(s)", len(notices))
    return notices


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _looks_like_url(s: str) -> bool:
    return bool(_URL_RE.match(s))
