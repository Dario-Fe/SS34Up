from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

try:
    from scraper.parsers import (
        ROME,
        TELEGRAM_CHANNEL_URL,
        assert_official_url,
        canonical_notice_url,
        extract_closure_window,
        extract_services,
        extract_validity,
        is_calendar_url,
        is_official_url,
        is_probably_duplicate_text,
        is_verbania_relevant,
        merge_services,
        notice_text,
        parse_calendar,
        parse_navlaghi_avvisi,
        parse_telegram_channel,
        parse_timetables,
        parse_verbania_article,
        parse_verbania_listing,
        short_hash,
        stable_hash,
    )
except ImportError:
    from parsers import (
        ROME,
        TELEGRAM_CHANNEL_URL,
        assert_official_url,
        canonical_notice_url,
        extract_closure_window,
        extract_services,
        extract_validity,
        is_calendar_url,
        is_official_url,
        is_probably_duplicate_text,
        is_verbania_relevant,
        merge_services,
        notice_text,
        parse_calendar,
        parse_navlaghi_avvisi,
        parse_telegram_channel,
        parse_timetables,
        parse_verbania_article,
        parse_verbania_listing,
        short_hash,
        stable_hash,
    )

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data.json"
USER_AGENT = "SS34Up/1.0 (monitoraggio indipendente SS34; dati pubblici)"
TIMEOUT = 45
RETRIES = 3
NOTICE_LOOKBACK_DAYS = 120

VERBANIA_BASE = "https://www.comune.verbania.it"
VERBANIA_LISTS = [
    f"{VERBANIA_BASE}/Novita/Avvisi",
    f"{VERBANIA_BASE}/Novita/Comunicati",
]
CALENDAR_URL = (
    f"{VERBANIA_BASE}/Novita/Comunicati/"
    "S.S.-34-a-Cannobio-il-calendario-delle-aperture-e-delle-chiusure-notturne"
)
PINNED_VERBANIA_URLS = [
    CALENDAR_URL,
    (
        f"{VERBANIA_BASE}/Novita/Avvisi/"
        "Lavori-sulla-SS-34-il-collegamento-notturno-tra-Cannero-e-Cannobio-passa-dal-lago"
    ),
    (
        f"{VERBANIA_BASE}/Novita/Avvisi/"
        "SS34-lavori-a-Cannobio-in-localita-Puncetta-dal-28-settembre-"
        "senso-unico-alternato-e-da-ottobre-chiusure-notturne"
    ),
    (
        f"{VERBANIA_BASE}/Novita/Avvisi/"
        "DA-LUNEDI-28-SETTEMBRE-AVVIO-DEL-CANTIERE-PER-LA-COSTRUZIONE-"
        "DELLA-GALLERIA-PARAMASSI-SULLA-SS-34-TRA-CANNERO-E-CANNOBIO"
    ),
]
NAV_API = "https://www.navigazionelaghi.it/wp-json/wp/v2/avvisi?lago=9&per_page=100"
NAV_TIMETABLES_URL = (
    "https://www.navigazionelaghi.it/biglietti-e-orari-lago-maggiore/"
)
TELEGRAM_URL = TELEGRAM_CHANNEL_URL
TELEGRAM_SOURCE = "Comune di Verbania · Telegram"
TELEGRAM_DEDUPE_DAYS = 3
DEDUPE_THRESHOLD = 0.65

SOURCE_CATALOG = [
    {
        "id": "comune-verbania",
        "name": "Comune di Verbania",
        "url": "https://www.comune.verbania.it/Novita",
        "kind": "istituzionale",
        "license": "CC BY 4.0 salvo contenuti di terzi",
    },
    {
        "id": "comune-verbania-telegram",
        "name": "Comune di Verbania · Canale Telegram",
        "url": TELEGRAM_URL,
        "kind": "istituzionale",
        "license": (
            "Contenuti del canale ufficiale, consultati dalla fonte; "
            "nessuna licenza aperta esplicita"
        ),
    },
    {
        "id": "navigazione-laghi",
        "name": "Navigazione Laghi",
        "url": "https://www.navigazionelaghi.it/",
        "kind": "istituzionale",
        "license": "Contenuti consultati dalla fonte ufficiale, senza licenza aperta esplicita",
    },
]


def log(message: str) -> None:
    print(message, file=sys.stderr)


def fetch(session: requests.Session, url: str) -> bytes:
    assert_official_url(url)
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code >= 500:
                raise requests.HTTPError(
                    f"HTTP {response.status_code}", response=response
                )
            response.raise_for_status()
            return response.content
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt + 1 < RETRIES:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Impossibile scaricare {url}: {last_error}")


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def first_seen_map(data: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for notice in data.get("notices", []):
        if notice.get("id") and notice.get("first_seen_at"):
            result[notice["id"]] = notice["first_seen_at"]
    return result


def infer_valid_from(body: str, published_at: str | None) -> str | None:
    if not published_at:
        return None
    try:
        year = datetime.fromisoformat(published_at).year
    except ValueError:
        return None
    match = re.search(
        r"(?:dal|a\s+partire\s+da)\s+"
        r"(?:giorno\s+|lunedì\s+|martedì\s+|mercoledì\s+|giovedì\s+|"
        r"venerdì\s+|sabato\s+|domenica\s+)?"
        r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)",
        body,
        re.IGNORECASE,
    )
    if not match:
        return None
    months = {
        "gennaio": 1,
        "febbraio": 2,
        "marzo": 3,
        "aprile": 4,
        "maggio": 5,
        "giugno": 6,
        "luglio": 7,
        "agosto": 8,
        "settembre": 9,
        "ottobre": 10,
        "novembre": 11,
        "dicembre": 12,
    }
    month = months.get(match.group(2).lower())
    if not month:
        return None
    try:
        return datetime(year, month, int(match.group(1)), tzinfo=ROME).date().isoformat()
    except ValueError:
        return None


def notice_tags(title: str, body: str) -> list[str]:
    text = f"{title} {body}"
    tags: list[str] = []
    if re.search(r"SS\s*\.?\s*34", text, re.IGNORECASE):
        tags.append("SS34")
    if re.search(r"Cannobio", text, re.IGNORECASE):
        tags.append("Cannobio")
    if re.search(r"Cannero", text, re.IGNORECASE):
        tags.append("Cannero Riviera")
    if re.search(r"navigaz|battell|traghett", text, re.IGNORECASE):
        tags.append("Navigazione")
    if re.search(r"chiusur|notte|notturn", text, re.IGNORECASE):
        tags.append("Chiusure notturne")
    return list(dict.fromkeys(tags))


def build_verbania_notice(
    article: dict,
    record: dict | None,
    first_seen_at: str,
    calendar_data: dict | None,
) -> dict:
    source_url = assert_official_url(article["source_url"])
    title = article["title"]
    body = article["body_text"]
    services = extract_services(body, source_url)
    closure = extract_closure_window(body)
    valid_from, valid_until = extract_validity(
        body,
        datetime.fromisoformat(article["published_at"]).year
        if article.get("published_at")
        else None,
    )
    if not valid_from:
        valid_from = infer_valid_from(body, article.get("published_at"))
    if closure:
        valid_from = closure.get("valid_from") or valid_from
        valid_until = closure.get("valid_until") or valid_until
    category = "viabilita"
    if is_calendar_url(source_url):
        category = "calendario"
    elif services:
        category = "navigazione"
    return {
        "id": f"comune-{short_hash(source_url)}",
        "source": "Comune di Verbania",
        "source_id": record.get("source_id", "") if record else "",
        "source_url": source_url,
        "category": category,
        "tags": notice_tags(title, body),
        "title": title,
        "summary": article["summary"],
        "body_text": body,
        "published_at": article.get("published_at", ""),
        "updated_at": article.get("updated_at", ""),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "closure_window": closure,
        "services": services,
        "is_calendar": bool(calendar_data),
        "calendar_updated_label": calendar_data.get("updated_label", "")
        if calendar_data
        else "",
        "content_hash": article["content_hash"],
        "first_seen_at": first_seen_at,
    }


def discover_verbania_records(session: requests.Session) -> list[dict]:
    records: list[dict] = []
    seen: set[str] = set()
    for base_url in VERBANIA_LISTS:
        for page in range(3):
            offset = page * 24
            url = base_url if offset == 0 else f"{base_url}/(offset)/{offset}"
            try:
                html = fetch(session, url)
            except RuntimeError as error:
                log(f"Avviso: {error}")
                break
            page_records = parse_verbania_listing(html, url)
            for record in page_records:
                if record["source_url"] in seen:
                    continue
                seen.add(record["source_url"])
                records.append(record)
            if len(page_records) < 24:
                break
    return records


def collect_verbania(
    session: requests.Session,
    existing: dict,
) -> tuple[dict | None, list[dict], list[str]]:
    warnings: list[str] = []
    records = discover_verbania_records(session)
    cutoff = datetime.now(ROME).date() - timedelta(days=NOTICE_LOOKBACK_DAYS)
    record_by_url: dict[str, dict] = {}
    for record in records:
        if not record.get("published_at"):
            continue
        try:
            published = date.fromisoformat(record["published_at"])
        except ValueError:
            continue
        if published < cutoff and record["source_url"] not in PINNED_VERBANIA_URLS:
            continue
        record_by_url[record["source_url"]] = record
    urls = list(record_by_url)
    for url in PINNED_VERBANIA_URLS:
        if url not in record_by_url:
            record_by_url[url] = {}
            urls.append(url)
    existing_by_url = {
        notice.get("source_url"): notice for notice in existing.get("notices", [])
    }
    seen = first_seen_map(existing)
    now = datetime.now(ROME).isoformat(timespec="seconds")
    calendar_data: dict | None = None
    notices: list[dict] = []
    fetched: set[str] = set()
    for url in urls:
        if url in fetched:
            continue
        fetched.add(url)
        try:
            html = fetch(session, url)
        except RuntimeError as error:
            warnings.append(str(error))
            previous = existing_by_url.get(url)
            if previous:
                notices.append(previous)
            continue
        try:
            article = parse_verbania_article(html, url)
        except Exception as error:
            warnings.append(f"Parsing fallito per {url}: {error}")
            previous = existing_by_url.get(url)
            if previous:
                notices.append(previous)
            continue
        if is_calendar_url(url):
            try:
                calendar_data = parse_calendar(html, url)
            except Exception as error:
                warnings.append(f"Calendario non interpretabile: {error}")
        if not (
            is_calendar_url(url)
            or is_verbania_relevant(article["title"], article["body_text"])
        ):
            continue
        notice = build_verbania_notice(
            article,
            record_by_url.get(url),
            seen.get(
                f"comune-{short_hash(url)}",
                now,
            ),
            calendar_data if is_calendar_url(url) else None,
        )
        notices.append(notice)
    notices.sort(
        key=lambda item: (
            item.get("published_at") or "",
            item.get("title") or "",
        ),
        reverse=True,
    )
    return calendar_data, notices, warnings


def notice_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def is_recent_notice(notice: dict) -> bool:
    published = notice_date(notice.get("published_at"))
    if not published:
        return True
    cutoff = datetime.now(ROME).date() - timedelta(days=NOTICE_LOOKBACK_DAYS)
    return published >= cutoff


def dedupe_context(known_notices: list[dict], candidate_date: date | None) -> list[str]:
    texts: list[str] = []
    for notice in known_notices:
        published = notice_date(notice.get("published_at"))
        if (
            candidate_date
            and published
            and abs((candidate_date - published).days) > TELEGRAM_DEDUPE_DAYS
        ):
            continue
        texts.append(notice_text(notice))
    return texts


def build_telegram_notice(
    post: dict,
    source_url: str,
    first_seen_at: str,
) -> dict:
    source_url = assert_official_url(source_url)
    title = post["title"]
    body = post["body_text"]
    services = extract_services(body, source_url)
    closure = extract_closure_window(body)
    reference_year = datetime.fromisoformat(post["published_at"]).year
    valid_from, valid_until = extract_validity(body, reference_year)
    if not valid_from:
        valid_from = infer_valid_from(body, post.get("published_at"))
    if closure:
        valid_from = closure.get("valid_from") or valid_from
        valid_until = closure.get("valid_until") or valid_until
    category = "navigazione" if services else "viabilita"
    tags = list(dict.fromkeys([*notice_tags(title, body), "Canale Telegram"]))
    return {
        "id": f"telegram-{post['id']}",
        "source": TELEGRAM_SOURCE,
        "source_id": post["id"],
        "source_url": source_url,
        "source_api": TELEGRAM_URL,
        "telegram_url": post["url"],
        "category": category,
        "tags": tags,
        "title": title,
        "summary": post["summary"],
        "body_text": body,
        "published_at": post["published_at"],
        "updated_at": post["published_at"],
        "valid_from": valid_from,
        "valid_until": valid_until,
        "closure_window": closure,
        "services": services,
        "is_calendar": False,
        "calendar_updated_label": "",
        "content_hash": stable_hash(
            {
                "title": title,
                "body": body,
                "published_at": post["published_at"],
                "source_url": source_url,
            }
        ),
        "first_seen_at": first_seen_at,
    }


def merge_missing_notices(
    existing: dict,
    current: list[dict],
    source: str,
) -> list[dict]:
    seen = {
        canonical_notice_url(notice["source_url"])
        for notice in current
        if notice.get("source_url")
    }
    merged = list(current)
    for notice in existing.get("notices", []):
        if notice.get("source") != source:
            continue
        source_url = notice.get("source_url")
        key = canonical_notice_url(source_url) if source_url else ""
        if key and key in seen:
            continue
        merged.append(notice)
        if key:
            seen.add(key)
    return merged


def filter_existing_telegram(
    previous: list[dict],
    known_notices: list[dict],
) -> list[dict]:
    known = list(known_notices)
    known_urls = {
        canonical_notice_url(notice["source_url"])
        for notice in known
        if notice.get("source_url")
    }
    accepted: list[dict] = []
    for notice in sorted(
        (item for item in previous if is_recent_notice(item)),
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    ):
        source_url = notice.get("source_url")
        key = canonical_notice_url(source_url) if source_url else ""
        if key and key in known_urls:
            continue
        candidate_date = notice_date(notice.get("published_at"))
        if is_probably_duplicate_text(
            notice_text(notice),
            dedupe_context(known, candidate_date),
            DEDUPE_THRESHOLD,
        ):
            continue
        accepted.append(notice)
        known.append(notice)
        if key:
            known_urls.add(key)
    return accepted


def collect_telegram(
    session: requests.Session,
    existing: dict,
    known_notices: list[dict],
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    seen = first_seen_map(existing)
    now = datetime.now(ROME).isoformat(timespec="seconds")
    try:
        payload = fetch(session, TELEGRAM_URL)
        posts = parse_telegram_channel(payload, TELEGRAM_URL)
    except Exception as error:
        warnings.append(f"Canale Telegram non disponibile: {error}")
        previous = [
            notice
            for notice in existing.get("notices", [])
            if notice.get("source") == TELEGRAM_SOURCE
        ]
        return filter_existing_telegram(previous, known_notices), warnings

    known = list(known_notices)
    known_urls = {
        canonical_notice_url(notice["source_url"])
        for notice in known
        if notice.get("source_url")
    }
    notices: list[dict] = []
    for post in sorted(
        posts,
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    ):
        title = post["title"]
        body = post["body_text"]
        if not is_verbania_relevant(title, body):
            continue
        official_links = [
            link for link in post["links"] if is_official_url(link)
        ]
        if any(
            canonical_notice_url(link) in known_urls
            for link in official_links
        ):
            continue
        candidate_date = notice_date(post.get("published_at"))
        if is_probably_duplicate_text(
            f"{title} {body}",
            dedupe_context(known, candidate_date),
            DEDUPE_THRESHOLD,
        ):
            continue
        source_url = official_links[0] if official_links else post["url"]
        notice = build_telegram_notice(
            post,
            source_url,
            seen.get(f"telegram-{post['id']}", now),
        )
        notices.append(notice)
        known.append(notice)
        known_urls.add(canonical_notice_url(source_url))

    current_ids = {notice["id"] for notice in notices}
    previous = [
        notice
        for notice in existing.get("notices", [])
        if notice.get("source") == TELEGRAM_SOURCE
        and notice.get("id") not in current_ids
    ]
    preserved = filter_existing_telegram(previous, known)
    return notices + preserved, warnings


def dedupe_by_source_url(notices: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for notice in notices:
        source_url = notice.get("source_url")
        key = canonical_notice_url(source_url) if source_url else ""
        if key and key in seen:
            continue
        result.append(notice)
        if key:
            seen.add(key)
    return result


def collect_navlaghi(
    session: requests.Session,
    existing: dict,
) -> tuple[list[dict], list[dict], list[str]]:
    warnings: list[str] = []
    seen = first_seen_map(existing)
    now = datetime.now(ROME).isoformat(timespec="seconds")
    try:
        payload = fetch(session, NAV_API)
        notices = parse_navlaghi_avvisi(payload, NAV_API)
    except Exception as error:
        warnings.append(f"Avvisi Navigazione Laghi non disponibili: {error}")
        notices = [
            notice
            for notice in existing.get("notices", [])
            if notice.get("source") == "Navigazione Laghi"
        ]
    for notice in notices:
        notice["first_seen_at"] = seen.get(notice["id"], notice.get("first_seen_at", now))
    try:
        html = fetch(session, NAV_TIMETABLES_URL)
        timetables = parse_timetables(html, NAV_TIMETABLES_URL)
    except Exception as error:
        warnings.append(f"Orari Navigazione Laghi non disponibili: {error}")
        timetables = existing.get("timetables", [])
    return notices, timetables, warnings


def build_data(
    calendar: dict,
    verbania_notices: list[dict],
    nav_notices: list[dict],
    telegram_notices: list[dict],
    timetables: list[dict],
) -> dict:
    notices = dedupe_by_source_url(
        verbania_notices + nav_notices + telegram_notices
    )
    notices.sort(
        key=lambda item: (
            item.get("published_at") or "",
            item.get("source") or "",
            item.get("title") or "",
        ),
        reverse=True,
    )
    services = merge_services(
        [
            notice.get("services", [])
            for notice in notices
        ]
        + [extract_services(calendar.get("body_text", ""), calendar["source_url"])]
    )
    core = {
        "calendar": {
            key: value
            for key, value in calendar.items()
            if key not in {"source", "title", "summary", "body_text"}
        },
        "notices": notices,
        "services": services,
        "timetables": timetables,
    }
    content_hash = stable_hash(core)
    return {
        "meta": {
            "app": "SS34Up",
            "version": 1,
            # Sempre l'ora del controllo appena eseguito: anche senza novità
            # il timestamp avanza, così l'app non sembra ferma.
            "generated_at": datetime.now(ROME).isoformat(timespec="seconds"),
            "timezone": "Europe/Rome",
            "update_schedule": ["10:00", "18:00"],
            "schedule_note": "Aggiornamento automatico alle 10:00 e 18:00, ora italiana.",
            "content_hash": content_hash,
            "sources": SOURCE_CATALOG,
        },
        "calendar": core["calendar"],
        "services": services,
        "notices": notices,
        "timetables": timetables,
    }


def write_data(path: Path, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggiorna data.json di SS34Up")
    parser.add_argument("--output", type=Path, default=DATA_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9",
        }
    )
    existing = load_existing(args.output)
    calendar, verbania_notices, warnings_verbania = collect_verbania(
        session, existing
    )
    if not calendar:
        previous_calendar = existing.get("calendar")
        if not previous_calendar:
            log("Errore: calendario SS34 non disponibile e nessun dato salvato.")
            return 1
        calendar = previous_calendar
        warnings_verbania.append(
            "Calendario SS34 non disponibile: uso l'ultimo calendario salvato."
        )
        verbania_notices = merge_missing_notices(
            existing, verbania_notices, "Comune di Verbania"
        )
    nav_notices, timetables, warnings_nav = collect_navlaghi(session, existing)
    telegram_notices, warnings_telegram = collect_telegram(
        session,
        existing,
        verbania_notices + nav_notices,
    )
    warnings = warnings_verbania + warnings_nav + warnings_telegram
    data = build_data(
        calendar,
        verbania_notices,
        nav_notices,
        telegram_notices,
        timetables,
    )
    for warning in warnings:
        log(f"Avviso: {warning}")
    if args.dry_run:
        print(json.dumps(data["meta"], ensure_ascii=False, indent=2))
        return 0
    write_data(args.output, data)
    log(
        f"Scritto {args.output} con {len(data['notices'])} avvisi, "
        f"{len(data['calendar']['days'])} giorni e {len(data['services'])} servizi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
