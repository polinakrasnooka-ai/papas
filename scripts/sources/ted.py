"""TED (EU Tenders Electronic Daily) search client.

Queries the public TED search API for recent notices matching our priority
CPV codes in priority countries. Returns normalized Notice objects for the
qualifier.

TED API docs: https://docs.ted.europa.eu/api/
Endpoint used: https://api.ted.europa.eu/v3/notices/search (POST, no auth needed
for public search).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging

import httpx

from scripts.config import (
    PRIORITY_CPV,
    PRIORITY_COUNTRIES_ISO3,
    PRODUCT_KEYWORDS,
    LOOKBACK_DAYS,
    MAX_NOTICES_PER_RUN,
)

log = logging.getLogger(__name__)

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

TED_FIELDS = [
    "publication-number",
    "notice-title",
    "publication-date",
    "deadline-date-lot",
    "buyer-name",
    "buyer-country",
    "place-of-performance",
    "classification-cpv",
    "notice-type",
    "procedure-type",
    "links",
]


@dataclass
class Notice:
    id: str
    title: str
    buyer: str
    country: str
    cpv: list[str]
    publication_date: str
    deadline: str | None
    notice_type: str
    url: str
    raw: dict = field(default_factory=dict, repr=False)


def _build_query(days: int) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    cpv_filter = " OR ".join(f"classification-cpv={c}" for c in PRIORITY_CPV)
    country_filter = " OR ".join(
        f"buyer-country={c}" for c in PRIORITY_COUNTRIES_ISO3
    )
    kw_filter = " OR ".join(f'notice-title~"{k}"' for k in PRODUCT_KEYWORDS)
    return (
        f"(publication-date>={since}) "
        f"AND ({country_filter}) "
        f"AND (({cpv_filter}) OR ({kw_filter}))"
    )


def fetch_recent_notices(days: int | None = None, limit: int | None = None) -> list[Notice]:
    days = days if days is not None else LOOKBACK_DAYS
    limit = limit if limit is not None else MAX_NOTICES_PER_RUN

    body = {
        "query": _build_query(days),
        "fields": TED_FIELDS,
        "limit": limit,
        "page": 1,
        "scope": "ALL",
    }
    log.info("TED query: %s (limit=%s)", body["query"], limit)

    with httpx.Client(timeout=60) as c:
        r = c.post(TED_SEARCH_URL, json=body, headers={"accept": "application/json"})
        r.raise_for_status()
        payload = r.json()

    notices = []
    for item in payload.get("notices", []):
        try:
            notices.append(_parse(item))
        except Exception as e:
            log.warning("skipping malformed TED item: %s", e)
    log.info("TED returned %d notices", len(notices))
    return notices


def _parse(item: dict) -> Notice:
    def _first(v):
        if isinstance(v, list) and v:
            return v[0]
        return v

    pub = _first(item.get("publication-number")) or _first(item.get("ND")) or ""
    title_val = item.get("notice-title") or item.get("TI") or ""
    if isinstance(title_val, dict):
        title = title_val.get("eng") or next(iter(title_val.values()), "")
    else:
        title = _first(title_val) or ""

    buyer = _first(item.get("buyer-name")) or _first(item.get("BUYER-NAME")) or ""
    if isinstance(buyer, dict):
        buyer = buyer.get("eng") or next(iter(buyer.values()), "")

    country = _first(item.get("buyer-country")) or _first(item.get("CY")) or ""
    cpv_raw = item.get("classification-cpv") or item.get("CPV") or []
    cpv = cpv_raw if isinstance(cpv_raw, list) else [cpv_raw]

    pub_date = _first(item.get("publication-date")) or _first(item.get("PD")) or ""
    deadline = _first(item.get("deadline-date-lot"))

    url = f"https://ted.europa.eu/en/notice/{pub}"
    links = item.get("links") or {}
    if isinstance(links, dict):
        html_link = links.get("html")
        if isinstance(html_link, dict):
            url = html_link.get("eng") or url
        elif isinstance(html_link, str):
            url = html_link

    return Notice(
        id=str(pub),
        title=str(title),
        buyer=str(buyer),
        country=str(country),
        cpv=[str(c) for c in cpv],
        publication_date=str(pub_date),
        deadline=str(deadline) if deadline else None,
        notice_type=str(_first(item.get("notice-type")) or ""),
        url=url,
        raw=item,
    )
