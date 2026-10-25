from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from html import unescape
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROME = ZoneInfo("Europe/Rome")
OFFICIAL_DOMAINS = {
    "comune.verbania.it",
    "www.comune.verbania.it",
    "navigazionelaghi.it",
    "www.navigazionelaghi.it",
}
TELEGRAM_CHANNEL = "VerbaniaMinforma"
TELEGRAM_CHANNEL_URL = f"https://t.me/s/{TELEGRAM_CHANNEL}"

MONTHS = {
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

STATUS_LABELS = {
    "APERTA": "Aperta",
    "CHIUSA": "Chiusa",
    "CHIUSURA_NOTTURNA": "Chiusura notturna",
    "NON_DEFINITA": "Non definita",
}

STATUS_SEVERITY = {
    "CHIUSA": 3,
    "CHIUSURA_NOTTURNA": 2,
    "NON_DEFINITA": 1,
    "APERTA": 0,
}

PLACE_NAMES = {
    "cannero": "Cannero Riviera",
    "cannero riviera": "Cannero Riviera",
    "cannobio": "Cannobio",
    "intra": "Intra",
    "laveno": "Laveno",
}

DEFAULT_DESTINATIONS = {
    "Cannero Riviera": "Cannobio",
    "Cannobio": "Cannero Riviera",
    "Intra": "Laveno",
    "Laveno": "Intra",
}

SERVICE_PATTERN = re.compile(
    r"(?:partenze?|partenza|da)\s+"
    r"(?P<from>cannero(?:\s+riviera)?|cannobio|intra|laveno)"
    r"(?:\s+(?:verso|a|per)\s+"
    r"(?P<to>cannero(?:\s+riviera)?|cannobio|intra|laveno))?"
    r"\s*(?::|alle|ore|verso)?\s*"
    r"(?P<times>(?:\d{1,2}[.,:]\d{2})(?:\s*[-–—]\s*\d{1,2}[.,:]\d{2})*)",
    re.IGNORECASE,
)

TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-4])[.:,](\d{2})(?!\d)")

SS34_PATTERN = re.compile(
    r"\bS\.?\s*S\.?\s*\.?\s*34\b|\bstatale\s*(?:n\.?\s*)?34\b|"
    r"\bSS\s*\.?\s*34\b",
    re.IGNORECASE,
)
LOCAL_PATTERN = re.compile(r"\bCannero\b|\bCannobio\b|\bPuncetta\b", re.IGNORECASE)
CONTEXT_PATTERN = re.compile(
    r"chiusur|senso unico|lavori|cantiere|galleria|paramassi|notturn|"
    r"navigaz|traghett|battell|collegamento|orari|parcheggi|pass\b",
    re.IGNORECASE,
)
EXCLUDE_PATTERN = re.compile(
    r"\bbando\b|\bconcorso\b|\bgraduatoria\b|\bassunzion|elezioni|referendum|"
    r"manifestazione|spettacolo|mostra|concerto|corso di|universit|"
    r"conferenza di servizi|indizione|procedimento|espropi|"
    r"progetto di fattibilit|pnrr|bandiera blu|giro d'italia|"
    r"pulizia versante|taglio selettivo|variante",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = unescape(value).replace("\xa0", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def node_text(node) -> str:
    return clean_text(node.get_text(" ", strip=True)) if node else ""


def parse_html(content: str | bytes) -> BeautifulSoup:
    return BeautifulSoup(content, "html.parser")


def meta_content(soup: BeautifulSoup, key: str, attr: str = "property") -> str:
    tag = soup.find("meta", attrs={attr: key})
    return clean_text(tag.get("content", "")) if tag else ""


def stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"t.me", "www.t.me"}:
        path = parsed.path.rstrip("/")
        return (
            path in {f"/{TELEGRAM_CHANNEL}", f"/s/{TELEGRAM_CHANNEL}"}
            or path.startswith(f"/{TELEGRAM_CHANNEL}/")
            or path.startswith(f"/s/{TELEGRAM_CHANNEL}/")
        )
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)


def assert_official_url(url: str) -> str:
    if not is_official_url(url):
        raise ValueError(f"URL non ufficiale: {url}")
    return url


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href)


def canonical_notice_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", unquote(parsed.path or "/")).rstrip("/") or "/"
    return f"https://{host}{path}" if host else clean_text(url)


DEDUPE_STOPWORDS = set(
    """
    a ad al alla alle allo anche che chi con da dal dalla dalle dallo dei del
    della delle dello di e ed gli ha hanno i il in io la le lo ma mi nei nel
    nella nelle nello non o per piu se si sono su sul sulla sulle tra un una
    uno come cosa cui dopo dove durante fra loro molto noi pero qua quale
    quali quando quanto sei sempre senza sia solo sopra sotto sta stato stata
    stati tutte tutti tutto vi voi the and for with from that this comune
    citta canale telegram informa verbania
    """.split()
)


def dedupe_tokens(text: str) -> frozenset[str]:
    value = re.sub(r"https?://\S+", " ", text or "")
    value = re.sub(r"\bS\.?\s*S\.?\s*\.?\s*34\b", " ss34 ", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\bstatale\s*(?:n\.?\s*)?34\b", " ss34 ", value, flags=re.IGNORECASE
    )
    value = re.sub(r"\bSS\s*\.?\s*34\b", " ss34 ", value, flags=re.IGNORECASE)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", value.lower())
    return frozenset(
        word
        for word in words
        if (len(word) >= 3 or word.isdigit()) and word not in DEDUPE_STOPWORDS
    )


def is_probably_duplicate_text(
    candidate_text: str,
    known_texts: list[str],
    threshold: float = 0.65,
) -> bool:
    candidate = dedupe_tokens(candidate_text)
    if not candidate:
        return False
    for known in known_texts:
        known_tokens = dedupe_tokens(known)
        if not known_tokens:
            continue
        union = candidate | known_tokens
        if len(candidate & known_tokens) / len(union) >= threshold:
            return True
    return False


def notice_text(notice: dict) -> str:
    return clean_text(
        " ".join(
            [
                notice.get("title") or "",
                notice.get("summary") or "",
                notice.get("body_text") or "",
            ]
        )
    )


def parse_telegram_datetime(value: str) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ROME).isoformat()


def telegram_title(lines: list[str]) -> str:
    for raw in lines:
        line = re.sub(r"^[^\wÀ-ÿ]+", "", raw).strip()
        if not re.search(r"[A-Za-zÀ-ÿ0-9]", line):
            continue
        if len(line) > 120:
            line = line[:120].rsplit(" ", 1)[0].rstrip(" ,;:-")
            return f"{line}…"
        return line
    return ""


def parse_telegram_channel(html: str | bytes, source_url: str) -> list[dict]:
    assert_official_url(source_url)
    soup = parse_html(html)
    posts: list[dict] = []
    for node in soup.select(".tgme_widget_message_wrap"):
        link = node.select_one(".tgme_widget_message_date[href]")
        time_node = node.select_one("time[datetime]")
        text_node = node.select_one(".tgme_widget_message_text")
        if not link or not time_node or not text_node:
            continue
        post_url = absolute_url(source_url, link.get("href", ""))
        if not is_official_url(post_url):
            continue
        published_at = parse_telegram_datetime(time_node.get("datetime", ""))
        if not published_at:
            continue
        lines = [
            clean_text(line)
            for line in text_node.get_text("\n", strip=True).splitlines()
            if clean_text(line)
        ]
        lines = [line for line in lines if re.search(r"[A-Za-zÀ-ÿ0-9]", line)]
        if not lines:
            continue
        body_text = clean_text(" ".join(lines))
        title = telegram_title(lines)
        if not title or not body_text:
            continue
        summary = body_text[:320].rstrip()
        if len(body_text) > 320:
            summary += "…"
        links: list[str] = []
        for anchor in text_node.find_all("a", href=True):
            href = anchor.get("href", "")
            candidate = href if href.startswith("http") else urljoin("https://t.me", href)
            if is_official_url(candidate) and candidate not in links:
                links.append(candidate)
        post_id = urlparse(post_url).path.rstrip("/").rsplit("/", 1)[-1]
        posts.append(
            {
                "id": post_id,
                "url": post_url,
                "published_at": published_at,
                "title": title,
                "summary": summary,
                "body_text": body_text,
                "links": links,
            }
        )
    return posts


def parse_italian_date(value: str, default_year: int | None = None) -> str | None:
    text = clean_text(value)
    numeric = re.search(r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?!\d)", text)
    if numeric:
        day, month, year = numeric.groups()
        year = int(year)
        if year < 100:
            year += 2000
        try:
            return date(year, int(month), int(day)).isoformat()
        except ValueError:
            return None
    textual = re.search(r"(?<!\d)(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})(?!\d)", text)
    if textual:
        day, month_name, year = textual.groups()
        month = MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day)).isoformat()
            except ValueError:
                return None
    if default_year:
        short = re.search(r"(?<!\d)(\d{1,2})\s+([A-Za-zÀ-ÿ]+)(?!\s+\d{4})", text)
        if short:
            day, month_name = short.groups()
            month = MONTHS.get(month_name.lower())
            if month:
                try:
                    return date(default_year, month, int(day)).isoformat()
                except ValueError:
                    return None
    return None


def parse_italian_datetime(value: str, default_year: int | None = None) -> str | None:
    text = clean_text(value)
    numeric = re.search(
        r"(?<!\d)(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?:\s+(\d{1,2})[:.,](\d{2}))?",
        text,
    )
    if numeric:
        day, month, year, hour, minute = numeric.groups()
        year = int(year)
        if year < 100:
            year += 2000
        try:
            dt = datetime(
                year,
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                tzinfo=ROME,
            )
            return dt.isoformat()
        except ValueError:
            return None
    day_iso = parse_italian_date(text, default_year)
    if day_iso:
        return f"{day_iso}T00:00:00+01:00"
    return None


def parse_wp_datetime(value: str) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ROME)
    return dt.isoformat()


def normalize_time(value: str) -> str | None:
    match = re.match(r"\s*(\d{1,2})[.:,](\d{2})\s*$", value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour == 24 and minute == 0:
        return "00:00"
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def extract_times(value: str) -> list[str]:
    times: list[str] = []
    for match in TIME_PATTERN.finditer(value or ""):
        normalized = normalize_time(f"{match.group(1)}.{match.group(2)}")
        if normalized and normalized not in times:
            times.append(normalized)
    return times


def normalize_calendar_status(value: str) -> str:
    text = clean_text(value).upper()
    if "CHIUSURA" in text and "NOTTUR" in text:
        return "CHIUSURA_NOTTURNA"
    if "CHIUS" in text:
        return "CHIUSA"
    if "APERT" in text:
        return "APERTA"
    return "NON_DEFINITA"


def parse_article_metadata(soup: BeautifulSoup) -> dict:
    title = meta_content(soup, "og:title") or node_text(soup.find("h1"))
    summary = meta_content(soup, "og:description") or meta_content(
        soup, "description", "name"
    )
    published_at = meta_content(soup, "article:published_time")
    updated_at = meta_content(soup, "article:modified_time")
    tags = [
        clean_text(tag.get("content", ""))
        for tag in soup.find_all("meta", attrs={"property": "article:tag"})
    ]
    published_label = ""
    updated_label = ""
    for node in soup.find_all(["small", "p", "h3"]):
        text = node_text(node)
        if text.startswith("Data:") and not published_label:
            published_label = text
        if text.startswith("Ultimo aggiornamento:") and not updated_label:
            updated_label = text
    if not published_at:
        published_at = parse_italian_datetime(published_label) or ""
    if not updated_at:
        updated_at = parse_italian_datetime(updated_label) or ""
    return {
        "title": clean_text(title),
        "summary": clean_text(summary),
        "published_at": published_at,
        "updated_at": updated_at,
        "published_label": published_label,
        "updated_label": updated_label.replace("Ultimo aggiornamento:", "").strip(),
        "tags": [tag for tag in tags if tag],
    }


def article_body(soup: BeautifulSoup) -> str:
    node = soup.select_one("article#corpo .richtext-wrapper")
    if not node:
        node = soup.select_one("article#corpo")
    if not node:
        node = soup.select_one("main") or soup
    return node_text(node)


def extract_closure_window(text: str) -> dict | None:
    candidates = []
    for match in re.finditer(
        r"dalle?\s+(?P<start>\d{1,2}[.:,]\d{2})\s+"
        r"(?:alle|fino\s+alle)\s+(?P<end>\d{1,2}[.:,]\d{2})",
        text,
        re.IGNORECASE,
    ):
        start = normalize_time(match.group("start"))
        end = normalize_time(match.group("end"))
        if not start or not end:
            continue
        candidates.append((match, start, end))
    if not candidates:
        return None
    selected = next(
        (
            candidate
            for candidate in candidates
            if int(candidate[1][:2]) >= 18 and int(candidate[2][:2]) <= 12
        ),
        candidates[0],
    )
    match, start, end = selected
    date_range = re.search(
        r"dal(?:la)?\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})\s+"
        r"(?:fino\s+al(?:la)?|al)\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    valid_from = parse_italian_date(date_range.group(1)) if date_range else None
    valid_until = parse_italian_date(date_range.group(2)) if date_range else None
    excluded: list[str] = []
    if re.search(r"notte\s+tra\s+sabato\s+e\s+domenica", text, re.IGNORECASE):
        excluded.append("sabato")
    if re.search(r"prefestivi\s*\(sabato\)|esclus[ai]\s+i\s+sabati", text, re.IGNORECASE):
        excluded.append("sabato")
    return {
        "start": start,
        "end": end,
        "timezone": "Europe/Rome",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "excluded_nights": sorted(set(excluded)),
    }


def extract_validity(text: str, reference_year: int | None = None) -> tuple[str | None, str | None]:
    patterns = [
        r"dal\s+(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})\s+(?:fino\s+)?al\s+(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})",
        r"dal\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})\s+(?:fino\s+)?al\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return parse_italian_date(match.group(1)), parse_italian_date(match.group(2))
    if reference_year:
        match = re.search(
            r"a\s+far\s+data\s+da\s+(?:[A-Za-zÀ-ÿ]+\s+)?(\d{1,2}\s+[A-Za-zÀ-ÿ]+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return parse_italian_date(match.group(1), reference_year), None
    return None, None


def extract_services(text: str, source_url: str) -> list[dict]:
    assert_official_url(source_url)
    services: list[dict] = []
    seen: set[tuple] = set()
    for match in SERVICE_PATTERN.finditer(clean_text(text)):
        origin = PLACE_NAMES.get(match.group("from").lower())
        if not origin:
            continue
        destination = (
            PLACE_NAMES.get(match.group("to").lower())
            if match.group("to")
            else DEFAULT_DESTINATIONS.get(origin)
        )
        if not destination or destination == origin:
            continue
        times = extract_times(match.group("times"))
        if not times:
            continue
        kind = "traghetto" if {origin, destination} == {"Intra", "Laveno"} else "battello"
        key = (origin, destination, kind, tuple(times))
        if key in seen:
            continue
        seen.add(key)
        services.append(
            {
                "id": f"servizio-{short_hash('|'.join([*key[:3], '-'.join(times)]))}",
                "kind": kind,
                "from": origin,
                "to": destination,
                "route": f"{origin} → {destination}",
                "times": times,
                "notes": (
                    "Corsa aggiuntiva serale"
                    if kind == "traghetto"
                    else "Servizio sostitutivo serale"
                ),
                "source_urls": [source_url],
            }
        )
    return services


def merge_services(groups: list[list[dict]]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for group in groups:
        for service in group:
            key = (
                service["from"],
                service["to"],
                service["kind"],
                tuple(service["times"]),
            )
            if key not in merged:
                merged[key] = {
                    **service,
                    "source_urls": list(dict.fromkeys(service.get("source_urls", []))),
                }
            else:
                for url in service.get("source_urls", []):
                    if url not in merged[key]["source_urls"]:
                        merged[key]["source_urls"].append(url)
    return sorted(
        merged.values(),
        key=lambda item: (
            0 if item["kind"] == "battello" else 1,
            item["from"],
            item["times"],
        ),
    )


def parse_calendar(html: str | bytes, source_url: str) -> dict:
    assert_official_url(source_url)
    soup = parse_html(html)
    metadata = parse_article_metadata(soup)
    article = soup.select_one("article#corpo") or soup
    rich = article.select_one(".richtext-wrapper") or article
    body_text = node_text(rich)
    months: list[dict] = []
    days: list[dict] = []
    for table in rich.select("table.table-striped"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = rows[0].find("th")
        header_text = node_text(header) if header else ""
        month_match = re.search(r"([A-Za-zÀ-ÿ]+)\s+(\d{4})", header_text)
        if not month_match:
            continue
        month = MONTHS.get(month_match.group(1).lower())
        year = int(month_match.group(2))
        if not month:
            continue
        weekdays = [
            node_text(cell).rstrip(".")
            for cell in rows[1].find_all("th")
        ] if len(rows) > 1 else []
        weeks: list[list[dict | None]] = []
        for row in rows[2:]:
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue
            week: list[dict | None] = []
            for cell in cells[:7]:
                pre = cell.find("pre")
                if not pre:
                    week.append(None)
                    continue
                day_text = node_text(pre)
                if not day_text.isdigit():
                    week.append(None)
                    continue
                paragraphs = " ".join(
                    node_text(paragraph) for paragraph in cell.find_all("p")
                )
                status = normalize_calendar_status(
                    paragraphs or node_text(cell).replace(day_text, "", 1)
                )
                day_number = int(day_text)
                try:
                    iso_date = date(year, month, day_number).isoformat()
                except ValueError:
                    week.append(None)
                    continue
                day = {
                    "date": iso_date,
                    "day": day_number,
                    "status": status,
                    "status_label": STATUS_LABELS[status],
                    "night_closed": status in {"CHIUSA", "CHIUSURA_NOTTURNA"},
                }
                week.append(day)
                days.append(day)
            if len(week) < 7:
                week.extend([None] * (7 - len(week)))
            if any(week):
                weeks.append(week)
        months.append(
            {
                "key": f"{year:04d}-{month:02d}",
                "label": f"{month_match.group(1).capitalize()} {year}",
                "year": year,
                "month": month,
                "weekdays": weekdays or ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
                "weeks": weeks,
            }
        )
    days.sort(key=lambda item: item["date"])
    counts = {
        status: sum(1 for day in days if day["status"] == status)
        for status in STATUS_LABELS
    }
    return {
        "source": "Comune di Verbania",
        "source_url": source_url,
        "title": metadata["title"],
        "summary": metadata["summary"],
        "published_at": metadata["published_at"],
        "updated_at": metadata["updated_at"],
        "updated_label": metadata["updated_label"],
        "body_text": body_text,
        "months": months,
        "days": days,
        "counts": counts,
        "closure_window": extract_closure_window(body_text),
        "content_hash": stable_hash(
            {
                "months": months,
                "published_at": metadata["published_at"],
                "updated_at": metadata["updated_at"],
            }
        ),
    }


def parse_verbania_listing(html: str | bytes, source_url: str) -> list[dict]:
    assert_official_url(source_url)
    soup = parse_html(html)
    records: list[dict] = []
    for card in soup.select("[data-object_id]"):
        heading = card.select_one("h3, h2")
        if not heading:
            continue
        title = node_text(heading)
        link = card.select_one("a.read-more[href]") or card.select_one("a[href]")
        if not link:
            continue
        url = absolute_url(source_url, link.get("href", ""))
        if not is_official_url(url):
            continue
        summary = ""
        for paragraph in card.select(".text-paragraph-card p"):
            text = node_text(paragraph)
            if "Data di pubblicazione" not in text:
                summary = text
                break
        published = ""
        for paragraph in card.find_all("p"):
            text = node_text(paragraph)
            if "Data di pubblicazione" in text:
                published = text
                break
        published_at = parse_italian_date(published)
        category = "Comunicati" if "/Comunicati/" in url else "Avvisi"
        records.append(
            {
                "source": "Comune di Verbania",
                "source_id": clean_text(card.get("data-object_id", "")),
                "source_url": url,
                "title": title,
                "summary": summary,
                "published_at": published_at or "",
                "category": category,
            }
        )
    return records


def parse_verbania_article(html: str | bytes, source_url: str) -> dict:
    assert_official_url(source_url)
    soup = parse_html(html)
    metadata = parse_article_metadata(soup)
    body_text = article_body(soup)
    return {
        "source": "Comune di Verbania",
        "source_url": source_url,
        "title": metadata["title"],
        "summary": metadata["summary"] or body_text[:300],
        "published_at": metadata["published_at"],
        "updated_at": metadata["updated_at"],
        "published_label": metadata["published_label"],
        "updated_label": metadata["updated_label"],
        "tags": metadata["tags"],
        "body_text": body_text,
        "content_hash": stable_hash(
            {
                "title": metadata["title"],
                "summary": metadata["summary"],
                "body_text": body_text,
                "published_at": metadata["published_at"],
                "updated_at": metadata["updated_at"],
            }
        ),
    }


def is_verbania_relevant(title: str, body: str) -> bool:
    text = f"{title} {body}"
    if EXCLUDE_PATTERN.search(text):
        return False
    has_ss34 = bool(SS34_PATTERN.search(text))
    has_local = bool(LOCAL_PATTERN.search(text))
    has_context = bool(CONTEXT_PATTERN.search(text))
    return has_ss34 and has_local and has_context


def is_calendar_url(url: str) -> bool:
    return "calendario-delle-aperture-e-delle-chiusure" in url.lower()


def parse_navlaghi_avvisi(payload: str | bytes | list, source_api: str) -> list[dict]:
    if isinstance(payload, (str, bytes)):
        data = json.loads(payload)
    else:
        data = payload
    notices: list[dict] = []
    for item in data:
        title = clean_text(
            parse_html(item.get("title", {}).get("rendered", "")).get_text(" ")
        )
        rendered = item.get("content", {}).get("rendered", "")
        body_text = node_text(parse_html(rendered))
        if not is_navlaghi_relevant(title, body_text):
            continue
        source_url = assert_official_url(item.get("link", ""))
        published_at = parse_wp_datetime(item.get("date", ""))
        updated_at = parse_wp_datetime(item.get("modified", ""))
        reference_year = (
            datetime.fromisoformat(published_at).year if published_at else None
        )
        valid_from, valid_until = extract_validity(body_text, reference_year)
        summary = body_text[:320].rstrip()
        if len(body_text) > 320:
            summary += "…"
        notices.append(
            {
                "id": f"navigazione-{item.get('id')}",
                "source": "Navigazione Laghi",
                "source_id": str(item.get("id", "")),
                "source_url": source_url,
                "source_api": source_api,
                "category": "navigazione",
                "tags": ["Navigazione Laghi", "Lago Maggiore"],
                "title": title,
                "summary": summary,
                "body_text": body_text,
                "published_at": published_at or "",
                "updated_at": updated_at or "",
                "valid_from": valid_from,
                "valid_until": valid_until,
                "closure_window": None,
                "services": [],
                "content_hash": stable_hash(
                    {
                        "title": title,
                        "body": body_text,
                        "modified": item.get("modified", ""),
                    }
                ),
            }
        )
    return notices


def is_navlaghi_relevant(title: str, body: str) -> bool:
    text = f"{title} {body}"
    if re.search(
        r"bonus\s+tpl|vendita\s+online|guasto\s+tecnico|sciopero",
        text,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"SS\s*\.?\s*34|Cannero|Cannobio|Intra\s*[-–]\s*Laveno",
            text,
            re.IGNORECASE,
        )
    )


def parse_timetables(html: str | bytes, source_url: str) -> list[dict]:
    assert_official_url(source_url)
    soup = parse_html(html)
    page_text = node_text(soup)
    valid_from, valid_until = extract_validity(page_text)
    timetables: dict[str, dict] = {}
    for link in soup.find_all("a", href=True):
        href = absolute_url(source_url, link["href"])
        if not href.lower().endswith(".pdf") or not is_official_url(href):
            continue
        label = node_text(link)
        combined = f"{label} {href}".upper()
        if "ARONA" in combined and "CANNOBIO" in combined:
            route = "Arona ↔ Cannobio"
            kind = "battello"
        elif "INTRA" in combined and "LAVENO" in combined:
            route = "Intra ↔ Laveno"
            kind = "traghetto"
        else:
            continue
        timetables[href] = {
            "id": f"orario-{short_hash(href)}",
            "kind": kind,
            "route": route,
            "title": label or route,
            "pdf_url": href,
            "source_page": source_url,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
    return sorted(timetables.values(), key=lambda item: (item["kind"], item["route"]))


def next_night_date(now: datetime) -> date:
    local = now.astimezone(ROME)
    if local.hour < 5:
        return (local.date()).fromordinal(local.date().toordinal() - 1)
    return local.date()
