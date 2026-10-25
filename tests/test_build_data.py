from __future__ import annotations

from datetime import datetime, timezone

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
