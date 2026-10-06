"""Orchestrator — one scheduled run of the pipeline.

Flow per run:
  1. Fetch recent TED notices in priority countries matching limestone CPVs.
  2. Skip anything already seen (SQLite).
  3. Qualify each new notice with Claude (+ web_search + web_fetch tools).
  4. Open the day with a greeting; if 0 new, send a "no news" wish; otherwise
     post one brief per qualifying notice.
  5. Record outcome in SQLite so the next run doesn't repeat.
"""
from __future__ import annotations
import logging
import sys
import time
from datetime import datetime, timezone

from scripts.config import GREETING_NAME, STATE_DB_PATH, check_env
from scripts.qualify import qualify_notice
from scripts.sources.ted import fetch_recent_notices
from scripts.state import State
from scripts.telegram import send_brief, send_text


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("run")


def _greeting() -> str:
    return f"Доброе утро, {GREETING_NAME}!"


def _no_news() -> str:
    return (
        f"{_greeting()} Сегодня новых тендеров нет. Хорошего дня!"
    )


def _header() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{_greeting()} Подборка за {today}."


def main() -> int:
    missing = check_env()
    if missing:
        log.error("missing env vars: %s", ", ".join(missing))
        return 1

    try:
        notices = fetch_recent_notices()
    except Exception as e:
        log.exception("TED fetch failed: %s", e)
        try:
            send_text(
                f"{_greeting()} TED временно недоступен, проверю позже. "
                "Хорошего дня!"
            )
        except Exception:
            pass
        return 2

    state = State(STATE_DB_PATH)
    try:
        new_notices = [n for n in notices if not state.is_seen(n.id)]
        log.info("TED total=%d, new=%d (not seen before)", len(notices), len(new_notices))

        if not new_notices:
            send_text(_no_news())
            return 0

        briefs: list[tuple[str, str]] = []
        skipped = errors = 0
        for n in new_notices:
            outcome, brief = qualify_notice(n)
            if outcome == "post" and brief:
                briefs.append((n.id, brief))
            elif outcome == "skip":
                skipped += 1
                state.mark(n.id, "skip")
            else:
                errors += 1
                state.mark(n.id, "error")
            time.sleep(0.5)

        if not briefs:
            send_text(_no_news())
            log.info(
                "run summary: posted=0 skipped=%d errors=%d (nothing qualified >=65)",
                skipped, errors,
            )
            return 0

        send_text(_header())
        time.sleep(0.5)

        posted = 0
        for notice_id, brief in briefs:
            try:
                send_brief(brief)
                posted += 1
                state.mark(notice_id, "post", brief)
            except Exception as e:
                log.exception("telegram send failed for %s: %s", notice_id, e)
                errors += 1
            time.sleep(1)

        log.info(
            "run summary: posted=%d skipped=%d errors=%d new=%d",
            posted, skipped, errors, len(new_notices),
        )
    finally:
        state.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
