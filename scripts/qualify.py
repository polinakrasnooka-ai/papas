"""Claude API wrapper that qualifies one TED notice into a bussiness brief.

Loads the agent system prompt from .claude/agents/limestone-leads.md and the
output format from docs/lead-template.md, then asks Claude to:
  1. apply the 21-point qualification checklist to the notice,
  2. score it internally,
  3. return either the brief (if scoring >= 65) or SKIP: <reason>.

For MVP we hand Claude only the TED notice metadata — the model has web
knowledge to make the UA-eligibility and logistics assessments, but will mark
anything unverified as «не подтверждено» per the system prompt.

Later we can wire WebSearch / WebFetch (via tool use) to let Claude open the
TED notice body, the SIWZ and SWPP2 for richer qualification.
"""
from __future__ import annotations
import logging

from anthropic import Anthropic

from scripts.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    AGENT_PROMPT_PATH,
    LEAD_TEMPLATE_PATH,
    SCORING_PATH,
)
from scripts.sources.ted import Notice

log = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    agent = AGENT_PROMPT_PATH.read_text(encoding="utf-8")
    template = LEAD_TEMPLATE_PATH.read_text(encoding="utf-8")
    scoring = SCORING_PATH.read_text(encoding="utf-8")
    return (
        agent
        + "\n\n# docs/lead-template.md (inlined)\n\n"
        + template
        + "\n\n# docs/scoring.md (inlined)\n\n"
        + scoring
    )


def _user_prompt(n: Notice) -> str:
    return (
        "Квалифицируй этот TED-notice как потенциальный лид для украинского "
        "экспортёра известняка. Применяй все правила system prompt'а.\n\n"
        f"TED ID: {n.id}\n"
        f"Заголовок: {n.title}\n"
        f"Покупатель: {n.buyer}\n"
        f"Страна покупателя: {n.country}\n"
        f"CPV: {', '.join(n.cpv) if n.cpv else '—'}\n"
        f"Опубликован: {n.publication_date}\n"
        f"Дедлайн: {n.deadline or '—'}\n"
        f"Тип уведомления: {n.notice_type}\n"
        f"URL уведомления: {n.url}\n\n"
        "Инструкции:\n"
        "1. Проведи внутреннюю оценку по рубрике docs/scoring.md.\n"
        "2. Если скоринг < 65 — верни одной строкой:\n"
        "   SKIP: <короткая причина, какого пункта не хватило>\n"
        "3. Если скоринг >= 65 — верни бизнес-brief в формате из "
        "docs/lead-template.md. Никакого скоринга, Tier, РЕШЕНИЯ, NEXT ACTION "
        "и прочих внутренних блоков в выдачу не включать.\n"
        "4. В brief обязательны кликабельные ссылки: TED-notice по URL выше, "
        "и — если известно — ссылка на supplier portal покупателя.\n"
        "5. Если данных мало и ты не можешь корректно оценить — SKIP: insufficient data.\n"
    )


def qualify_notice(notice: Notice) -> tuple[str, str | None]:
    """Returns (outcome, brief).

    outcome: "post" | "skip" | "error"
    brief:   non-empty markdown brief when outcome == "post", else None.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    system = _load_system_prompt()
    user = _user_prompt(notice)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        log.exception("Anthropic call failed for %s: %s", notice.id, e)
        return "error", None

    text = "".join(
        block.text for block in msg.content if getattr(block, "type", None) == "text"
    ).strip()

    if text.upper().startswith("SKIP"):
        log.info("skip %s: %s", notice.id, text[:120])
        return "skip", None
    if not text:
        return "error", None
    return "post", text
