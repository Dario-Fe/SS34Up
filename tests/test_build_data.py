from __future__ import annotations

from datetime import datetime, timedelta, timezone

from parsers import ROME
from scraper_ss34up import build_data

CALENDAR = {
    "source_url": "https://www.comune.verbania.it/Novita/Comunicati/esempio",
    "body_text": "",
    "days": [],
}


def build_data_once() -> dict:
    return build_data(dict(CALENDAR), [], [], [], [])


def test_generated_at_reflects_the_run_even_without_changes() -> None:
    data = build_data_once()
    generated = datetime.fromisoformat(data["meta"]["generated_at"])

    assert generated.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - generated).total_seconds()) < 60


def test_content_hash_stays_stable_when_nothing_changes() -> None:
    first = build_data_once()
    second = build_data_once()

    assert first["meta"]["content_hash"] == second["meta"]["content_hash"]


def test_build_data_includes_telegram_override() -> None:
    now = datetime.now(ROME)
    night = (now - timedelta(days=1)).date() if now.hour < 5 else now.date()
    calendar = {
        "source_url": "https://www.comune.verbania.it/Novita/Comunicati/esempio",
        "body_text": "",
        "days": [
            {
                "date": night.isoformat(),
                "status": "CHIUSA",
                "night_closed": True,
            }
        ],
    }
    notice = {
        "source": "Comune di Verbania · Telegram",
        "title": "SS34 aperta stanotte",
        "summary": "",
        "body_text": "La SS34 resterà aperta stanotte per pioggia.",
        "published_at": now.isoformat(),
        "source_url": "https://t.me/s/VerbaniaMinforma/1",
        "telegram_url": "https://t.me/s/VerbaniaMinforma/1",
        "services": [],
    }

    data = build_data(calendar, [], [], [notice], [])

    overrides = data["calendar"]["overrides"]
    assert len(overrides) == 1
    assert overrides[0]["date"] == night.isoformat()
    assert overrides[0]["status"] == "APERTA"
    assert overrides[0]["night_closed"] is False
    assert overrides[0]["kind"] == "auto"
