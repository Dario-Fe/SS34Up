from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers import (
    canonical_notice_url,
    extract_closure_window,
    extract_services,
    extract_times,
    extract_validity,
    is_navlaghi_relevant,
    is_official_url,
    is_probably_duplicate_text,
    is_verbania_relevant,
    merge_services,
    normalize_time,
    parse_calendar,
    parse_navlaghi_avvisi,
    parse_telegram_channel,
    parse_telegram_datetime,
    parse_timetables,
    parse_verbania_article,
    parse_verbania_listing,
)

FIXTURES = Path(__file__).parent / "fixtures"
CALENDAR_URL = (
    "https://www.comune.verbania.it/Novita/Comunicati/"
    "S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne"
)
SERVICES_URL = (
    "https://www.comune.verbania.it/Novita/Avvisi/"
    "Lavori-sulla-SS-34-il-collegamento-notturno-tra-Cannero-e-Cannobio-passa-dal-lago"
)
ORDINANCE_URL = (
    "https://www.comune.verbania.it/Novita/Avvisi/"
    "SS34-lavori-a-Cannobio-in-localita-Puncetta-dal-28-settembre-"
    "senso-unico-alternato-e-da-ottobre-chiusure-notturne"
)
PROGRAM_URL = (
    "https://www.comune.verbania.it/Novita/Avvisi/"
    "DA-LUNEDI-28-SETTEMBRE-AVVIO-DEL-CANTIERE-PER-LA-COSTRUZIONE-"
    "DELLA-GALLERIA-PARAMASSI-SULLA-SS-34-TRA-CANNERO-E-CANNOBIO"
)
NAV_API = "https://www.navigazionelaghi.it/wp-json/wp/v2/avvisi?lago=9&per_page=100"
NAV_ORARI = "https://www.navigazionelaghi.it/biglietti-e-orari-lago-maggiore/"


@pytest.fixture(scope="module")
def calendar():
    return parse_calendar((FIXTURES / "verbania_calendar.html").read_bytes(), CALENDAR_URL)


def test_calendar_has_three_months_and_all_days(calendar):
    assert [month["label"] for month in calendar["months"]] == [
        "Ottobre 2026",
        "Novembre 2026",
        "Dicembre 2026",
    ]
    assert len(calendar["days"]) == 81
    assert len(calendar["months"][0]["weeks"][1]) == 7


def test_calendar_statuses_are_normalized(calendar):
    days = {day["date"]: day for day in calendar["days"]}
    assert days["2026-10-21"]["status"] == "CHIUSURA_NOTTURNA"
    assert days["2026-10-22"]["status"] == "CHIUSA"
    assert days["2026-10-24"]["status"] == "APERTA"
    assert days["2026-10-25"]["status"] == "APERTA"
    assert days["2026-11-01"]["status"] == "APERTA"
    assert days["2026-10-21"]["night_closed"] is True
    assert days["2026-10-24"]["night_closed"] is False


def test_calendar_metadata_and_closure_window(calendar):
    assert calendar["updated_label"] == "21/10/2026 09:05"
    assert calendar["updated_at"].startswith("2026-10-21T09:05")
    assert calendar["closure_window"]["start"] == "21:00"
    assert calendar["closure_window"]["end"] == "05:00"
    assert calendar["closure_window"]["excluded_nights"] == ["sabato"]


def test_calendar_services_are_extracted(calendar):
    services = extract_services(calendar["body_text"], CALENDAR_URL)
    routes = {service["route"]: service["times"] for service in services}
    assert routes["Cannero Riviera → Cannobio"] == [
        "21:05",
        "22:00",
        "23:00",
        "00:00",
    ]
    assert routes["Cannobio → Cannero Riviera"] == [
        "21:30",
        "22:30",
        "23:30",
        "00:30",
    ]
    assert routes["Intra → Laveno"] == ["00:00"]
    assert routes["Laveno → Intra"] == ["00:30"]


def test_article_metadata_and_services():
    article = parse_verbania_article(
        (FIXTURES / "verbania_services.html").read_bytes(), SERVICES_URL
    )
    assert "Cannero e Cannobio" in article["title"]
    assert article["published_at"].startswith("2026-10-09")
    assert article["updated_at"].startswith("2026-10-09T16:33")
    services = extract_services(article["body_text"], SERVICES_URL)
    assert len(services) == 4
    assert services[0]["kind"] == "battello"
    assert services[2]["kind"] == "traghetto"


def test_ordinance_validity_and_closure():
    article = parse_verbania_article(
        (FIXTURES / "verbania_ordinance.html").read_bytes(), ORDINANCE_URL
    )
    closure = extract_closure_window(article["body_text"])
    assert closure["start"] == "21:00"
    assert closure["end"] == "05:00"
    assert closure["valid_from"] == "2026-10-12"
    assert closure["valid_until"] == "2027-05-31"
    assert closure["excluded_nights"] == ["sabato"]
    assert extract_validity(article["body_text"], 2026) == (
        "2026-10-12",
        "2027-05-31",
    )


def test_program_chooses_night_closure_not_day_restrictions():
    article = parse_verbania_article(
        (FIXTURES / "verbania_program.html").read_bytes(), PROGRAM_URL
    )
    closure = extract_closure_window(article["body_text"])
    assert closure["start"] == "21:00"
    assert closure["end"] == "05:00"


def test_listing_is_parsed_with_official_urls():
    records = parse_verbania_listing(
        (FIXTURES / "verbania_listing.html").read_bytes(),
        "https://www.comune.verbania.it/Novita/Avvisi",
    )
    assert len(records) == 24
    assert records[0]["source_id"] == "10473"
    assert records[0]["published_at"] == "2026-10-19"
    assert records[0]["source_url"].startswith("https://www.comune.verbania.it/")
    assert all(is_official_url(record["source_url"]) for record in records)


def test_relevance_excludes_local_but_unrelated_notices():
    assert is_verbania_relevant(
        "SS34, lavori a Cannobio",
        "Chiusura notturna dalle 21:00 alle 05:00 per la galleria paramassi.",
    )
    assert not is_verbania_relevant(
        "Viabilità, asfaltature notturne in via Troubetzkoy",
        "Senso unico alternato notturno ai Tre Ponti.",
    )
    assert not is_verbania_relevant(
        "Conferenza di Servizi decisoria – Indizione",
        "SS34 e Cannobio: avvio del procedimento.",
    )


def test_navlaghi_filters_out_non_local_alerts():
    notices = parse_navlaghi_avvisi(
        (FIXTURES / "navigazione_avvisi.json").read_bytes(), NAV_API
    )
    titles = {notice["title"] for notice in notices}
    assert len(notices) == 2
    assert "Apertura SS.34 Cannero – Cannobio" in titles
    assert "Rimodulazione servizio di linea" in titles
    assert not any("bonus" in title.lower() for title in titles)
    assert not any("guasto" in title.lower() for title in titles)
    assert all(is_official_url(notice["source_url"]) for notice in notices)


def test_navlaghi_validity_is_inferred_from_reference_year():
    notices = parse_navlaghi_avvisi(
        (FIXTURES / "navigazione_avvisi.json").read_bytes(), NAV_API
    )
    riduzione = next(
        notice for notice in notices if notice["title"] == "Rimodulazione servizio di linea"
    )
    assert riduzione["valid_from"] == "2026-10-21"
    assert riduzione["valid_until"] is None
    assert riduzione["published_at"].startswith("2026-10-12T17:32")


def test_timetables_are_parsed_with_validity():
    timetables = parse_timetables(
        (FIXTURES / "navigazione_orari.html").read_bytes(), NAV_ORARI
    )
    assert len(timetables) == 2
    routes = {item["route"]: item for item in timetables}
    assert routes["Arona ↔ Cannobio"]["valid_from"] == "2026-10-05"
    assert routes["Arona ↔ Cannobio"]["valid_until"] == "2026-11-08"
    assert routes["Intra ↔ Laveno"]["kind"] == "traghetto"
    assert routes["Intra ↔ Laveno"]["pdf_url"].endswith(".pdf")


def test_time_and_service_helpers():
    assert normalize_time("24.00") == "00:00"
    assert normalize_time("21,05") == "21:05"
    assert extract_times("21.05 – 22.00 – 24.00") == ["21:05", "22:00", "00:00"]
    first = extract_services(
        "Da Cannero: 21.05 - 22.00",
        "https://www.comune.verbania.it/Novita/Avvisi/test",
    )
    second = extract_services(
        "Da Cannero: 21.05 - 22.00",
        "https://www.comune.verbania.it/Novita/Comunicati/test",
    )
    merged = merge_services([first, second])
    assert len(merged) == 1
    assert len(merged[0]["source_urls"]) == 2


def test_official_url_validation():
    assert is_official_url("https://www.comune.verbania.it/Novita/Avvisi")
    assert is_official_url("https://www.navigazionelaghi.it/avvisi/test/")
    assert is_official_url("https://t.me/VerbaniaMinforma")
    assert is_official_url("https://t.me/s/VerbaniaMinforma")
    assert is_official_url("https://t.me/VerbaniaMinforma/2891")
    assert is_official_url("https://t.me/s/VerbaniaMinforma/2891")
    assert not is_official_url("http://t.me/VerbaniaMinforma")
    assert not is_official_url("https://t.me/OtherChannel/2891")
    assert not is_official_url("http://www.comune.verbania.it/Novita/Avvisi")
    assert not is_official_url("https://example.com/fake")
    assert not is_official_url("https://comune.verbania.it.evil.example/fake")


def test_telegram_channel_parser():
    posts = parse_telegram_channel(
        (FIXTURES / "telegram_verbania.html").read_bytes(),
        "https://t.me/s/VerbaniaMinforma",
    )
    assert len(posts) == 4
    by_id = {post["id"]: post for post in posts}
    assert by_id["2891"]["published_at"] == "2026-10-09T16:54:15+02:00"
    assert by_id["2891"]["title"].startswith("SS 34 chiusa di notte")
    assert "galleria paramassi" in by_id["2891"]["body_text"]
    assert by_id["2891"]["links"] == []
    assert by_id["2902"]["links"] == [
        "https://www.comune.verbania.it/Novita/Comunicati/"
        "S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne"
    ]
    assert by_id["2902"]["url"] == "https://t.me/VerbaniaMinforma/2902"
    assert parse_telegram_datetime("2026-10-09T16:54:15+02:00") == (
        "2026-10-09T16:54:15+02:00"
    )
    assert parse_telegram_datetime("not-a-date") is None


def test_telegram_text_dedupe_and_canonical_url():
    known = [
        "SS 34 chiusa di notte a Cannobio: dal 21 ottobre battelli sostitutivi "
        "tra Cannero e Cannobio. Durante i lavori per la galleria paramassi, "
        "Navigazione Lago Maggiore attiva quattro corse notturne tra Cannero e Cannobio."
    ]
    candidate = (
        "SS 34 chiusa di notte a Cannobio: dal 21 ottobre battelli sostitutivi "
        "tra Cannero e Cannobio. Durante i lavori per la galleria paramassi, "
        "Navigazione Lago Maggiore attiva quattro corse notturne tra Cannero e Cannobio."
    )
    assert is_probably_duplicate_text(candidate, known)
    assert not is_probably_duplicate_text(
        "SS 34 chiusa per lavori urgenti a Cannobio il 27 ottobre.", known
    )
    assert canonical_notice_url(
        "https://www.comune.verbania.it/Novita/Avvisi/test/?utm_source=x#top"
    ) == "https://comune.verbania.it/Novita/Avvisi/test"


def test_collect_telegram_skips_duplicates(monkeypatch):
    import scraper_ss34up as scraper

    html = (FIXTURES / "telegram_verbania.html").read_bytes()
    monkeypatch.setattr(scraper, "fetch", lambda session, url: html)
    known = [
        {
            "source": "Comune di Verbania",
            "source_url": CALENDAR_URL,
            "title": "S.S. 34 a Cannobio, da domani la chiusura notturna",
            "summary": "",
            "body_text": "Calendario delle aperture e delle chiusure notturne.",
            "published_at": "2026-10-20T17:00:00+02:00",
        },
        {
            "source": "Comune di Verbania",
            "source_url": (
                "https://www.comune.verbania.it/Novita/Avvisi/"
                "SS34-chiusa-di-notte-battelli-sostitutivi"
            ),
            "title": "SS 34 chiusa di notte a Cannobio",
            "summary": "",
            "body_text": (
                "SS 34 chiusa di notte a Cannobio: dal 21 ottobre battelli "
                "sostitutivi tra Cannero e Cannobio. Durante i lavori per la "
                "galleria paramassi, Navigazione Lago Maggiore attiva quattro "
                "corse notturne tra Cannero e Cannobio."
            ),
            "published_at": "2026-10-09T16:00:00+02:00",
        },
    ]
    existing = {
        "notices": [
            {
                "id": "telegram-2800",
                "source": scraper.TELEGRAM_SOURCE,
                "source_url": "https://t.me/VerbaniaMinforma/2800",
                "title": "SS 34: senso unico alternato a Cannero",
                "summary": "",
                "body_text": "SS 34: senso unico alternato a Cannero il 2 ottobre per lavori.",
                "published_at": "2026-10-01T10:00:00+02:00",
            },
            {
                "id": "telegram-2500",
                "source": scraper.TELEGRAM_SOURCE,
                "source_url": "https://t.me/VerbaniaMinforma/2500",
                "title": "SS 34: vecchio avviso",
                "summary": "",
                "body_text": "SS 34: vecchio avviso non più recente.",
                "published_at": "2025-10-01T10:00:00+02:00",
            },
        ]
    }
    notices, warnings = scraper.collect_telegram(None, existing, known)
    assert warnings == []
    assert [notice["id"] for notice in notices] == [
        "telegram-2910",
        "telegram-2800",
    ]
    notice = notices[0]
    assert notice["source"] == scraper.TELEGRAM_SOURCE
    assert notice["source_url"] == "https://t.me/VerbaniaMinforma/2910"
    assert notice["telegram_url"] == "https://t.me/VerbaniaMinforma/2910"
    assert "Canale Telegram" in notice["tags"]
    assert is_official_url(notice["source_url"])
    assert notice["first_seen_at"]


def test_merge_missing_notices_keeps_previous_comune_fallback():
    import scraper_ss34up as scraper

    current = [
        {
            "source": "Comune di Verbania",
            "source_url": "https://www.comune.verbania.it/Novita/Avvisi/current",
        }
    ]
    existing = {
        "notices": [
            {
                "source": "Comune di Verbania",
                "source_url": "https://www.comune.verbania.it/Novita/Avvisi/current",
            },
            {
                "source": "Comune di Verbania",
                "source_url": "https://www.comune.verbania.it/Novita/Avvisi/old",
            },
            {
                "source": "Navigazione Laghi",
                "source_url": "https://www.navigazionelaghi.it/avvisi/old",
            },
        ]
    }
    merged = scraper.merge_missing_notices(existing, current, "Comune di Verbania")
    assert [notice["source_url"] for notice in merged] == [
        "https://www.comune.verbania.it/Novita/Avvisi/current",
        "https://www.comune.verbania.it/Novita/Avvisi/old",
    ]


def test_notice_body_contains_no_navigation_chrome():
    article = parse_verbania_article(
        (FIXTURES / "verbania_services.html").read_bytes(), SERVICES_URL
    )
    assert "Vai al contenuto principale" not in article["body_text"]
    assert "Contatta il comune" not in article["body_text"]
    assert "Partenze da Cannero" in article["body_text"]


def test_generated_data_contract():
    data = json.loads((Path(__file__).parent.parent / "data.json").read_text("utf-8"))
    assert data["meta"]["app"] == "SS34Up"
    assert data["meta"]["update_schedule"] == ["10:00", "18:00"]
    assert data["meta"]["timezone"] == "Europe/Rome"
    assert len(data["calendar"]["days"]) == 81
    assert len(data["services"]) == 4
    assert len(data["timetables"]) == 2
    assert data["notices"]
    assert all(is_official_url(notice["source_url"]) for notice in data["notices"])
    assert all(notice["first_seen_at"] for notice in data["notices"])
    assert all(is_official_url(item["pdf_url"]) for item in data["timetables"])
