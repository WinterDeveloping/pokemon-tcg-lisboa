"""Write the events out as an iCalendar (.ics) feed.

Google Calendar and Apple Calendar both consume this format. Subscribing to it at
a URL keeps the calendar live; importing the file once produces a static snapshot.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from events import Event

PRODID = "-//lisbon-tcg-events//Pokemon TCG Lisboa//PT"
CAL_NAME = "Pokémon TCG · Lisboa"
TZID = "Europe/Lisbon"

# How long each event type usually runs, used to give the calendar entry an end time.
DURATIONS_H = {
    "League Cup": 6,
    "League Challenge": 4,
    "Pre-Release": 4,
}
DEFAULT_DURATION_H = 4

# Self-contained timezone definition so no tzdata package is needed at runtime.
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Lisbon
X-LIC-LOCATION:Europe/Lisbon
BEGIN:DAYLIGHT
DTSTART:19700329T010000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
TZOFFSETFROM:+0000
TZOFFSETTO:+0100
TZNAME:WEST
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:19701025T020000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
TZOFFSETFROM:+0100
TZOFFSETTO:+0000
TZNAME:WET
END:STANDARD
END:VTIMEZONE"""


def _escape(text: str) -> str:
    """Escape a value for an iCalendar TEXT field (RFC 5545 3.3.11)."""
    return (str(text)
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Fold a content line to 75 octets, continuing with a leading space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line

    chunks, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        # Continuation lines carry a leading space, so budget one octet less.
        limit = 75 if not chunks else 74
        if len(current) + len(encoded) > limit:
            chunks.append(current)
            current = b""
        current += encoded
    chunks.append(current)
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def build(events: list[Event], radius_km: float = 30.0) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(CAL_NAME)}",
        f"X-WR-CALDESC:{_escape(f'Cups, Challenges e Pre-Releases ate {radius_km:.0f} km de Lisboa')}",
        f"X-WR-TIMEZONE:{TZID}",
        # Hints to clients that polling more than twice a day is pointless.
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        *VTIMEZONE.splitlines(),
    ]

    for event in events:
        # The pokedata guid is stable, so re-subscribing updates rather than duplicates.
        uid = f"{event.guid or event.date.isoformat() + event.shop}@pokedata.ovh"
        summary = f"{event.label} · {event.shop}"

        detail = [event.label]
        if event.cost:
            detail.append(f"Custo: {event.cost}")
        detail.append(f"{event.city} · {event.km:.0f} km de Lisboa")
        if event.url:
            detail.append(event.url)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"SUMMARY:{_escape(summary)}",
        ]

        if event.time:
            hours = DURATIONS_H.get(event.label, DEFAULT_DURATION_H)
            start = datetime.combine(
                event.date,
                datetime.strptime(event.time, "%H:%M").time(),
            )
            end = start + timedelta(hours=hours)
            lines += [
                f"DTSTART;TZID={TZID}:{start:%Y%m%dT%H%M%S}",
                f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}",
            ]
        else:
            # No usable start time: an all-day entry beats inventing one.
            lines += [
                f"DTSTART;VALUE=DATE:{event.date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{event.date + timedelta(days=1):%Y%m%d}",
            ]

        if event.address:
            lines.append(f"LOCATION:{_escape(event.address)}")
        if event.url:
            lines.append(f"URL:{event.url}")

        lines += [
            f"DESCRIPTION:{_escape(chr(10).join(detail))}",
            f"CATEGORIES:{_escape(event.label)}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def write(events: list[Event], out_path: Path, radius_km: float = 30.0) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build(events, radius_km), encoding="utf-8", newline="")
    return out_path
