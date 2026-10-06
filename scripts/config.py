"""Runtime configuration — reads env vars, defines priority CPV / countries / keywords."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")

GREETING_NAME = os.environ.get("GREETING_NAME", "Евгений")
HOME_BASE = os.environ.get("HOME_BASE", "Кодыма, Одесская обл., Украина")

STATE_DB_PATH = REPO_ROOT / "state.sqlite"

AGENT_PROMPT_PATH = REPO_ROOT / ".claude" / "agents" / "limestone-leads.md"
LEAD_TEMPLATE_PATH = REPO_ROOT / "docs" / "lead-template.md"
SCORING_PATH = REPO_ROOT / "docs" / "scoring.md"
SOURCES_DOC_PATH = REPO_ROOT / "docs" / "sources.md"

LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "7"))
MAX_NOTICES_PER_RUN = int(os.environ.get("MAX_NOTICES_PER_RUN", "50"))

# Приоритет из Кодымы, Одесская обл.: Дунай-плечо (RO, BG, RS, HR, BA, SI)
# идёт первым, Чоп-плечо (HU, SK) вторым, Польша и Германия — замыкают.
# Молдова (MDA) не в TED (не ЕС) — её тендеры собираются отдельно через
# scripts/sources/moldova.py (mtender.gov.md, achizitii.md).
PRIORITY_COUNTRIES_ISO3 = [
    "ROU", "BGR", "SRB", "HRV", "BIH", "SVN",
    "HUN", "SVK",
    "POL", "CZE", "AUT", "DEU",
    "MKD", "MNE", "ALB", "XKX",
]

# Жёсткое исключение. Эти страны не рассматриваются как покупатели,
# как транзит, как источник конкурентов для сравнения, и вообще не
# упоминаются в brief'ах. Основание: санкции ЕС/США/Украины, невозможность
# коммерческой логистики из UA, этическая/комплаенс-позиция.
BLOCKED_COUNTRIES_ISO3 = ["RUS", "BLR"]
BLOCKED_COUNTRIES_HUMAN = ["Россия", "Беларусь", "Приднестровье (ПМР)"]

PRIORITY_CPV = [
    "14212100",
    "14212200",
    "14212330",
    "14211000",
    "14212000",
    "44921000",
    "44921200",
    "44921300",
]

PRODUCT_KEYWORDS = [
    "limestone", "calcium carbonate", "flux limestone",
    "wapień", "sorbent wapienny", "mączka wapienna", "węglan wapnia",
    "calcar", "carbonat de calciu",
    "vápenec", "vápenná múčka", "uhličitan vápenatý",
    "mészkő", "mészkőliszt", "kalcium-karbonát",
    "Kalkstein", "Kalksteinmehl", "Kalkmehl", "REA-Kalkstein", "Hüttenkalk",
    "vapnenac", "varovik", "apnenec", "кречњак", "варовик",
]


def check_env() -> list[str]:
    """Return list of missing required env vars (empty = all good)."""
    missing = []
    for name in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID"):
        if not os.environ.get(name):
            missing.append(name)
    return missing
