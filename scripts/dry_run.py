"""Dry-run harness — exercises the orchestration end-to-end without
spending money or needing real secrets.

Stubs out:
- TED fetcher: returns 2 handcrafted notices (Румыния + Болгария)
- Moldova sweep: returns 1 handcrafted notice (Lafarge Rezina)
- Anthropic qualifier: returns a canned brief for one notice, SKIP for another
- Telegram sender: prints what WOULD be sent to stdout, grouped by message

Runs three scenarios:
  Scenario A — fresh state, 3 new notices → greeting + briefs
  Scenario B — same state, nothing new → "сегодня новостей нет"
  Scenario C — error path: TED down → graceful morning message

Does NOT need ANTHROPIC_API_KEY / TELEGRAM_* env vars. Safe to run anywhere.
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dry-run-stub")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:dry-run-stub")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "@dry-run")

from scripts import run as runner  # noqa: E402
from scripts.sources.ted import Notice  # noqa: E402


SENT: list[tuple[str, str]] = []  # (kind, text) per Telegram call


def _mk_notices() -> list[Notice]:
    return [
        Notice(
            id="DRY-RO-001",
            title="Furnizare calcar măcinat pentru desulfurare FGD — CE Oltenia",
            buyer="Complexul Energetic Oltenia S.A.",
            country="ROU",
            cpv=["14212100", "44921300"],
            publication_date="2026-10-01",
            deadline="2026-11-15",
            notice_type="Contract notice",
            url="https://ted.europa.eu/en/notice/DRY-RO-001",
        ),
        Notice(
            id="DRY-BG-001",
            title="Доставка на варовик за IOS — ТЕЦ Марица Изток 2",
            buyer="TPP Maritsa East 2 EAD",
            country="BGR",
            cpv=["14212100"],
            publication_date="2026-10-03",
            deadline="2026-10-20",
            notice_type="Contract notice",
            url="https://ted.europa.eu/en/notice/DRY-BG-001",
        ),
    ]


def _mk_moldova_notices() -> list[Notice]:
    return [
        Notice(
            id="md:dryrun-md-001",
            title="Achiziție calcar pentru producție — Lafarge Ciment Rezina",
            buyer="Lafarge Ciment (Moldova) S.A.",
            country="MDA",
            cpv=[],
            publication_date="2026-10-04",
            deadline="2026-10-25",
            notice_type="MD-tender",
            url="https://mtender.gov.md/tenders/DRY-MD-001",
        ),
    ]


def _fake_qualify(notice: Notice) -> tuple[str, str | None]:
    if notice.country == "BGR":
        return "skip", None
    if notice.country == "ROU":
        return "post", (
            f"**{notice.buyer} — CE Oltenia Rovinari (Румыния)**\n\n"
            f"- **Покупатель:** {notice.buyer}, Târgu Jiu / Rovinari\n"
            "- **Отрасль:** лигнитная ТЭС, FGD-sorbent потребитель\n"
            "- **Что закупает:** calcar măcinat для IOS\n"
            f"- **Форма:** open tender, деадлайн {notice.deadline}\n"
            "- **Статус:** активная\n"
            "- **Объём:** ~50 000 т/год (отраслевая оценка)\n"
            "- **Техтребования:** CaCO₃ ≥ 95%, фракция 0–3 мм, EN 12620\n"
            "- **Прошлые поставщики:** Holcim Romania, не подтверждено\n"
            "- **Логистика:** ХОРОШАЯ (из Кодымы ~400 км авто/жд через Рени → Галац)\n"
            "- **Допуск UA:** вероятно, DCFTA UA-EU открывает рынок; подтвердить в SIWZ\n\n"
            "**Ссылки:**\n"
            f"- Тендер: [DRY-RO-001]({notice.url})\n"
            "- Portal: [SEAP / e-licitatie.ro](https://www.e-licitatie.ro/)"
        )
    if notice.country == "MDA":
        return "post", (
            f"**{notice.buyer} — Rezina (Молдова)**\n\n"
            f"- **Покупатель:** {notice.buyer}, Rezina\n"
            "- **Отрасль:** cement — крупнейшая цементная площадка MD\n"
            "- **Что закупает:** calcar sort, партии до 500 т\n"
            f"- **Форма:** rolling RFQ, следующий окно до {notice.deadline}\n"
            "- **Статус:** активная\n"
            "- **Объём:** не подтверждено\n"
            "- **Техтребования:** внутренняя спека Lafarge\n"
            "- **Прошлые поставщики:** внутренний карьер Lafarge + MD-добытчики\n"
            "- **Логистика:** ХОРОШАЯ (~130 км авто из Кодымы, Рыбница / Единцы)\n"
            "- **Допуск UA:** вероятно, UA-MD прямые торговые отношения\n\n"
            "**Ссылки:**\n"
            f"- Тендер: [MTender Moldova]({notice.url})\n"
            "- Portal: [mtender.gov.md](https://mtender.gov.md/)"
        )
    return "skip", None


def _fake_send_text(text: str) -> None:
    SENT.append(("text", text))


def _fake_send_brief(text: str) -> None:
    SENT.append(("brief", text))


def _print_sent(label: str) -> None:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    if not SENT:
        print("(ничего не отправлено)")
        return
    for i, (kind, text) in enumerate(SENT, 1):
        print(f"\n--- Telegram сообщение #{i} [{kind}] ---")
        print(text)
    print(f"\nИтого: {len(SENT)} сообщений")


def _reset(state_path: Path) -> None:
    SENT.clear()
    if state_path.exists():
        state_path.unlink()


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="limestone-dryrun-"))
    state_path = tmpdir / "state.sqlite"

    orig_check_env = runner.check_env
    orig_fetch = runner.fetch_recent_notices
    orig_sweep = runner.sweep_moldova
    orig_qualify = runner.qualify_notice
    orig_send_text = runner.send_text
    orig_send_brief = runner.send_brief
    orig_state_path = runner.STATE_DB_PATH

    runner.STATE_DB_PATH = state_path
    runner.check_env = lambda: []
    runner.qualify_notice = _fake_qualify
    runner.send_text = _fake_send_text
    runner.send_brief = _fake_send_brief

    # also neutralize the 0.5s/1s sleeps between messages for a fast test
    import scripts.run as _run_mod
    _run_mod.time.sleep = lambda *_: None

    try:
        print("\n########  SCENARIO A: fresh state, 3 new tenders  ########")
        _reset(state_path)
        runner.fetch_recent_notices = _mk_notices
        runner.sweep_moldova = _mk_moldova_notices
        rc = runner.main()
        print(f"\nexit code: {rc}")
        _print_sent("TELEGRAM OUTPUT (scenario A)")

        print("\n\n########  SCENARIO B: same state, nothing new  ########")
        SENT.clear()
        # DON'T reset state — simulating 'next day same tenders already seen'
        rc = runner.main()
        print(f"\nexit code: {rc}")
        _print_sent("TELEGRAM OUTPUT (scenario B)")

        print("\n\n########  SCENARIO C: TED fetch error  ########")
        _reset(state_path)

        def _blow(*_a, **_kw):
            raise RuntimeError("TED timeout (simulated)")

        runner.fetch_recent_notices = _blow
        runner.sweep_moldova = _mk_moldova_notices
        rc = runner.main()
        print(f"\nexit code: {rc}")
        _print_sent("TELEGRAM OUTPUT (scenario C)")

    finally:
        runner.check_env = orig_check_env
        runner.fetch_recent_notices = orig_fetch
        runner.sweep_moldova = orig_sweep
        runner.qualify_notice = orig_qualify
        runner.send_text = orig_send_text
        runner.send_brief = orig_send_brief
        runner.STATE_DB_PATH = orig_state_path

    return 0


if __name__ == "__main__":
    sys.exit(main())
