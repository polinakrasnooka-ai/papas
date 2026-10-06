"""Claude API wrapper that qualifies one TED notice into a business brief.

Loads the agent system prompt from .claude/agents/limestone-leads.md and the
output format from docs/lead-template.md, then asks Claude to:
  1. apply the 21-point qualification checklist to the notice,
  2. score it internally against docs/scoring.md,
  3. return either the brief (if scoring >= 65) or SKIP: <reason>.

Enables Anthropic server tools `web_search_20260209` and `web_fetch_20260209`
so the model can open the TED notice body, SIWZ, supplier portal, company site,
and do LinkedIn / Google X-Ray for procurement contacts and previous suppliers —
turning the thin TED metadata into a real-world qualification.
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
    GREETING_NAME,
    HOME_BASE,
)
from scripts.sources.ted import Notice

log = logging.getLogger(__name__)

WEB_SEARCH_MAX_USES = 5
WEB_FETCH_MAX_USES = 10

ALLOWED_RESEARCH_DOMAINS = [
    "ted.europa.eu",
    "op.europa.eu",
    "ec.europa.eu",
    "ezamowienia.gov.pl",
    "uzp.gov.pl",
    "e-licitatie.ro",
    "anap.gov.ro",
    "uvo.gov.sk",
    "josephine.proebiz.com",
    "ekr.gov.hu",
    "kozbeszerzes.hu",
    "nen.nipez.cz",
    "vestnikverejnychzakazek.cz",
    "mtender.gov.md",
    "achizitii.md",
    "evergabe-online.de",
    "service.bund.de",
    "vergabe24.de",
    "dtvp.de",
    "bbg.gv.at",
    "ankoe.at",
    "jnportal.ujn.gov.rs",
    "eojn.hr",
    "app.eop.bg",
    "enarocanje.si",
    "ejn.gov.ba",
    "linkedin.com",
    "google.com",
]


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
        + f"\n\n# Контекст заказчика\n\n"
        + f"- Заказчик: {GREETING_NAME}\n"
        + f"- База отгрузки: {HOME_BASE}\n"
        + "- Логистика считается ИЗ этой базы, не из абстрактной Украины.\n"
    )


def _user_prompt(n: Notice) -> str:
    return (
        "Квалифицируй этот TED-notice как потенциальный лид. Применяй все "
        "правила system prompt'а.\n\n"
        f"TED ID: {n.id}\n"
        f"Заголовок: {n.title}\n"
        f"Покупатель: {n.buyer}\n"
        f"Страна покупателя: {n.country}\n"
        f"CPV: {', '.join(n.cpv) if n.cpv else '—'}\n"
        f"Опубликован: {n.publication_date}\n"
        f"Дедлайн: {n.deadline or '—'}\n"
        f"Тип уведомления: {n.notice_type}\n"
        f"URL уведомления: {n.url}\n\n"
        "Процедура:\n"
        "1. Открой URL уведомления через web_fetch — прочитай тело notice, "
        "   warunki udziału / requisite / conditions, бенефициара, объёмы, "
        "   technical spec, bid bond, страны-участники, предыдущих поставщиков.\n"
        "2. Через web_search найди supplier portal покупателя (SWPP2, Ariba, "
        "   Jaggaer и т.п.), сайт площадки, предыдущие аналогичные тендеры.\n"
        "3. При необходимости — LinkedIn X-Ray через Google: "
        "   `site:linkedin.com/in \"procurement\" \"<buyer>\"`.\n"
        "4. Оцени по 21-пунктовому чеклисту и рубрике скоринга.\n"
        "5. Логистика — ИЗ Кодымы, Одесская обл. (не из Львова). Приоритет: "
        "   RO, MD, BG, RS, HR, BA (Дунай, короткое плечо авто/жд). PL/CZ/SK/"
        "   HU — умеренно (нужен расчёт freight). DE/AT — только если крупно "
        "   и UA допущен.\n\n"
        "Вывод:\n"
        "- Если скоринг < 65 → одна строка: `SKIP: <что не прошло>`.\n"
        "- Если скоринг >= 65 → бизнес-brief в формате docs/lead-template.md. "
        "  Никаких блоков со скорингом, Tier, РЕШЕНИЕМ, NEXT ACTION — они "
        "  только для внутренней отсечки.\n"
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

    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": WEB_SEARCH_MAX_USES,
            "allowed_domains": ALLOWED_RESEARCH_DOMAINS,
        },
        {
            "type": "web_fetch_20260209",
            "name": "web_fetch",
            "max_uses": WEB_FETCH_MAX_USES,
            "citations": {"enabled": True},
        },
    ]

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=3000,
            system=system,
            tools=tools,
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
