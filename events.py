"""Fetch Pokemon TCG premier events (Cups, Challenges, Pre-Releases) near Lisbon.

Data comes from pokedata.ovh's undocumented table API. It is a hobby site with no
SLA, so results are cached to disk and every field is read defensively.
"""

import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path

import requests

API_URL = "https://www.pokedata.ovh/events/tableapi/index_table.php"
CACHE_PATH = Path(__file__).with_name(".cache_events.json")
PAST_CACHE_PATH = Path(__file__).with_name(".cache_events_past.json")
CACHE_TTL_SECONDS = 6 * 60 * 60

LISBON_LAT, LISBON_LON = 38.7223, -9.1393
PORTO_LAT, PORTO_LON = 41.1496, -8.6109

# Radius that counts as "the metro area" for the two big cities.
METRO_KM = 40.0

# The page opens here, and events.ics has always been this feed.
HOME_PLACE = "Lisboa"

# pokedata stores city names unaccented; these are the ones that surface as
# headings on the site, so they are worth spelling properly.
CITY_ACCENTS = {
    "Evora": "Évora",
    "Portimao": "Portimão",
    "Setubal": "Setúbal",
    "Alges": "Algés",
    "Belem": "Belém",
    "Vila Nova De Famalicao": "Vila Nova de Famalicão",
    "Santo Andre": "Santo André",
}

# Far enough to cover the mainland and the islands; the API is country-wide
# anyway, so this only switches off the distance filter.
NATIONAL_KM = 2000.0


def place_slug(place: str) -> str:
    """URL-safe form of a place name: 'Portimão' -> 'portimao'."""
    plain = unicodedata.normalize("NFKD", place).encode("ascii", "ignore").decode()
    return "-".join(plain.lower().split())


def place_feed(place: str) -> str:
    """Filename of the feed for one place."""
    if place == HOME_PLACE:
        return "events.ics"  # unchanged since launch; subscribers depend on it
    return f"events-{place_slug(place)}.ics"

BAD = "�"  # replacement char: accents already lost in pokedata's own database

# Repair the mangled names that actually occur in the Lisbon area.
MOJIBAKE_FIXES = {
    "ALG" + BAD + "S": "ALGÉS",
    "BEL" + BAD + "M": "BELÉM",
    "SANTO ANDR" + BAD: "SANTO ANDRÉ",
    "SET" + BAD + "BAL": "SETÚBAL",
}

# type -> (display label, sort weight). Cups outrank Challenges on the same day.
TYPE_LABELS = {
    "League Cup": ("League Cup", 0),
    "League Challenge": ("League Challenge", 1),
    "Prerelease": ("Pre-Release", 2),
    "Pre Release": ("Pre-Release", 2),
}


@dataclass
class Event:
    date: date
    time: str
    type: str
    shop: str
    city: str
    address: str
    cost: str
    place: str
    km: float
    url: str
    guid: str

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.type, (self.type, 9))[0]

    @property
    def weight(self) -> int:
        return TYPE_LABELS.get(self.type, (self.type, 9))[1]


def _titlecase(text: str) -> str:
    """Title-case an ALL CAPS name without breaking apostrophes (PLAYER'S -> Player's)."""
    return re.sub(
        r"[^\W\d_]+(?:'[^\W\d_]+)?",
        lambda m: m.group(0)[0].upper() + m.group(0)[1:],
        text.lower(),
    )


def _clean(text: str) -> str:
    """Repair known bad names, then strip any remaining replacement characters."""
    text = (text or "").strip()
    for bad, good in MOJIBAKE_FIXES.items():
        text = text.replace(bad, good)
    return unicodedata.normalize("NFC", text.replace(BAD, ""))


def _clean_cost(raw: str) -> str:
    """Normalise the free-text cost field into something displayable."""
    raw = _clean(raw).rstrip("-").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d+([.,]\d+)?", raw):
        return raw.replace(",", ".") + "€"
    return _titlecase(raw)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    radius = 6371.0
    rad = math.radians
    dlat = rad(lat2 - lat1)
    dlon = rad(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _city_name(raw: str) -> str:
    """Display form of a city: title-cased, with known accents restored."""
    name = _titlecase(_clean(raw).split(",")[0])
    return CITY_ACCENTS.get(name, name)


def _place(lat: float, lon: float, city: str) -> str:
    """Which place heading an event belongs under.

    Suburbs of the two big cities collapse into them, so "Lisboa" means the
    metro area rather than the 3 events whose city field literally says
    Lisboa. Everywhere else keeps its own name.

    Decided on coordinates, not pokedata's city field, which is unreliable:
    one shop 16 km from Lisbon reports its city as "Torres Novas".
    """
    if _haversine_km(LISBON_LAT, LISBON_LON, lat, lon) <= METRO_KM:
        return "Lisboa"
    if _haversine_km(PORTO_LAT, PORTO_LON, lat, lon) <= METRO_KM:
        return "Porto"
    return city


def _request_page(page: int, past: bool = False) -> list[dict]:
    """One page of Portuguese premier TCG events.

    Country-wide queries return 100 rows per page; the API's lat/lon+radius mode
    returns only one row per page, so distance is filtered client-side instead.

    past=True also returns events that have already happened. pokedata keeps
    roughly the last two months, so anything older simply is not available.
    """
    payload = {
        "past": "1" if past else "", "country": "PT", "city": "", "shop": "", "league": "",
        "states": "[]", "postcode": "",
        # TCG premier events only.
        "cups": "1", "challenges": "1", "prereleases": "1", "premier": "1",
        # "Friendly TCG" is the weekly casual league night - excluded.
        "ftcg": "",
        # Video game and Pokemon GO events - excluded.
        "vcups": "", "vchallenges": "", "fvg": "",
        "go": "", "gocup": "", "fgo": "", "mss": "",
        "latitude": "", "longitude": "", "radius": "", "unit": "km",
        "width": 1920, "page": page,
    }
    response = requests.post(
        API_URL,
        json=payload,
        headers={"Accept": "application/json", "User-Agent": "lisbon-tcg-events/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _fetch_raw(use_cache: bool = True, past: bool = False) -> list[dict]:
    # Upcoming and past responses are cached apart so one cannot mask the other.
    cache_path = PAST_CACHE_PATH if past else CACHE_PATH
    if use_cache and cache_path.exists():
        if time.time() - cache_path.stat().st_mtime < CACHE_TTL_SECONDS:
            return json.loads(cache_path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    for page in range(10):  # generous ceiling; Portugal fits in one page today
        batch = _request_page(page, past=past)
        if not batch:
            break
        rows.extend(batch)

    cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def _to_events(rows: list[dict], radius_km: float) -> list[Event]:
    """Turn raw API rows into Events within radius_km, sorted by date."""
    events: list[Event] = []

    for row in rows:
        try:
            when = datetime.strptime(row["date"], "%Y-%m-%d").date()
            km = _haversine_km(LISBON_LAT, LISBON_LON, float(row["latitude"]), float(row["longitude"]))
        except (KeyError, ValueError, TypeError):
            continue  # skip rows with a missing or unparseable date/coordinate

        if km > radius_km:
            continue

        clock = ""
        raw_time = (row.get("when") or "").strip()
        if " " in raw_time:
            clock = raw_time.split(" ", 1)[1][:5]
            if clock in ("00:00", "01:00"):
                clock = ""  # placeholder timestamps, not real start times

        events.append(Event(
            date=when,
            time=clock,
            type=(row.get("type") or "").strip(),
            shop=_titlecase(_clean(row.get("shop", ""))),
            city=_city_name(row.get("city", "")),
            address=_titlecase(_clean(row.get("street_address", ""))),
            cost=_clean_cost(row.get("cost", "")),
            place=_place(float(row["latitude"]), float(row["longitude"]),
                         _city_name(row.get("city", ""))),
            km=km,
            url=(row.get("pokemon_url") or "").strip(),
            guid=(row.get("guid") or "").strip(),
        ))

    events.sort(key=lambda e: (e.date, e.weight, e.shop))
    return events


def get_events(radius_km: float = 30.0, use_cache: bool = True) -> list[Event]:
    """Upcoming Cups, Challenges and Pre-Releases within radius_km of Lisbon."""
    today = date.today()
    return [e for e in _to_events(_fetch_raw(use_cache=use_cache), radius_km) if e.date >= today]


def get_past_events(radius_km: float = 30.0, weeks: int = 8,
                    use_cache: bool = True) -> list[Event]:
    """Events from the last `weeks` weeks, oldest first.

    pokedata only keeps about two months of history, so a longer window just
    returns whatever it still has rather than failing.
    """
    today = date.today()
    start = today - timedelta(weeks=weeks)
    rows = _fetch_raw(use_cache=use_cache, past=True)
    return [e for e in _to_events(rows, radius_km) if start <= e.date < today]
