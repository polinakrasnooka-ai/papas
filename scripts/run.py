"""Orchestrator — one scheduled run of the pipeline.

Flow per run:
  1. Fetch recent TED notices in priority countries matching limestone CPVs
     or keywords.
  2. Skip anything already seen (SQLite).
  3. Qualify each new notice with Claude -> brief (or SKIP).
  4. Post each brief to the Telegram channel.
  5. Record outcome in SQLite so the next run doesn't repeat.

Exit codes:
  0 — ran cleanly (even if 0 new notices)
  1 — missing env vars
  2 — upstream fetch error
"""
from __future__ import annotations
import logging
import sys
import time

from scripts.config import STATE_DB_PATH, check_env
from scripts.qualify import qualify_notice
from scripts.sources.ted import fetch_recent_notices
from scripts.state import State
from scripts.telegram import send_brief


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("run")


def main() -> int:
    missing = check_env()
    if missing:
        log.error("missing env vars: %s", ", ".join(missing))
        return 1

    try:
        notices = fetch_recent_notices()
    except Exception as e:
        log.exception("TED fetch failed: %s", e)
        return 2

    state = State(STATE_DB_PATH)
    try:
        posted = skipped = errors = already = 0
        for n in notices:
            if state.is_seen(n.id):
                already += 1
                continue
            outcome, brief = qualify_notice(n)
            if outcome == "post" and brief:
                try:
                    send_brief(brief)
                    posted += 1
                    state.mark(n.id, "post", brief)
                except Exception as e:
                    log.exception("telegram send failed for %s: %s", n.id, e)
                    errors += 1
            elif outcome == "skip":
                skipped += 1
                state.mark(n.id, "skip")
            else:
                errors += 1
                state.mark(n.id, "error")
            time.sleep(0.5)
    finally:
        state.close()

    log.info(
        "run summary: posted=%d skipped=%d errors=%d already_seen=%d total=%d",
        posted, skipped, errors, already, len(notices),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
