"""Lisbon Pokemon TCG event tracker.

  python main.py                       # print the list and write events.png
  python main.py --weeks 6             # only the next 6 weeks
  python main.py --radius 15           # tighter than the default 30 km
  python main.py --discord <webhook>   # post the image to a Discord channel
  python main.py --ics                 # also write events.ics for Google/Apple Calendar
  python main.py --past-ics            # also write past.ics (the last 8 weeks)
  python main.py --refresh             # bypass the 6 hour cache
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

import calendar_feed
from events import get_events, get_past_events, place_feed, NATIONAL_KM
from poster import render

OUT_PATH = Path(__file__).with_name("events.png")
ICS_PATH = Path(__file__).with_name("events.ics")
PAST_ICS_PATH = Path(__file__).with_name("past.ics")


def post_to_discord(webhook_url: str, image_path: Path, count: int) -> None:
    """Upload the poster to a Discord channel via an incoming webhook."""
    content = f"**Pokémon TCG · Lisboa** — {count} eventos a caminho \N{ELECTRIC LIGHT BULB}"
    with image_path.open("rb") as handle:
        response = requests.post(
            webhook_url,
            data={"content": content},
            files={"file": (image_path.name, handle, "image/png")},
            timeout=30,
        )
    response.raise_for_status()


def write_place_feeds(out_dir: Path, weeks: int | None, past_weeks: int,
                      use_cache: bool) -> list[tuple[str, int]]:
    """Write the national feeds the website reads, plus one feed per city.

    events.ics stays the Lisbon feed it has always been, so anyone already
    subscribed keeps getting exactly the events they signed up for.
    """
    events = get_events(radius_km=NATIONAL_KM, use_cache=use_cache)
    past = get_past_events(radius_km=NATIONAL_KM, weeks=past_weeks, use_cache=use_cache)
    if weeks:
        cutoff = date.today() + timedelta(weeks=weeks)
        events = [e for e in events if e.date <= cutoff]

    written = []

    def emit(filename: str, evs, scope):
        calendar_feed.write(evs, out_dir / filename, radius_km=NATIONAL_KM, scope=scope)
        written.append((filename, len(evs)))

    # What the page itself reads: everything, filtered client-side.
    emit("all.ics", events, "Portugal")
    emit("all-past.ics", past, "Portugal")

    # Busiest first, which is also the order the pills end up in.
    places = sorted({e.place for e in events},
                    key=lambda p: (-sum(e.place == p for e in events), p))
    for place in places:
        emit(place_feed(place), [e for e in events if e.place == place], place)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Pokemon TCG events near Lisbon")
    parser.add_argument("--radius", type=float, default=30.0, help="km from Lisbon centre (default 30)")
    parser.add_argument("--weeks", type=int, default=None, help="only include the next N weeks")
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="PNG output path")
    parser.add_argument("--discord", metavar="WEBHOOK_URL", help="post the image to a Discord webhook")
    parser.add_argument("--refresh", action="store_true", help="ignore the local cache")
    parser.add_argument("--ics", nargs="?", const=ICS_PATH, type=Path, metavar="PATH",
                        help="also write an .ics calendar feed")
    parser.add_argument("--past-ics", nargs="?", const=PAST_ICS_PATH, type=Path, metavar="PATH",
                        help="also write an .ics of recently finished events")
    parser.add_argument("--past-weeks", type=int, default=8,
                        help="how far back --past-ics reaches (default 8)")
    parser.add_argument("--places", metavar="DIR", type=Path,
                        help="write the national feeds plus one per city into DIR")
    parser.add_argument("--no-poster", action="store_true",
                        help="skip the PNG (for CI, where the Windows fonts are absent)")
    args = parser.parse_args()

    try:
        events = get_events(radius_km=args.radius, use_cache=not args.refresh)
    except requests.RequestException as exc:
        print(f"Could not reach pokedata.ovh: {exc}", file=sys.stderr)
        return 1

    if args.weeks:
        cutoff = date.today() + timedelta(weeks=args.weeks)
        events = [e for e in events if e.date <= cutoff]

    if args.places:
        try:
            written = write_place_feeds(args.places, weeks=args.weeks,
                                        past_weeks=args.past_weeks,
                                        use_cache=not args.refresh)
        except requests.RequestException as exc:
            print(f"Could not build the city feeds: {exc}", file=sys.stderr)
            return 1
        for name, n in written:
            print(f"{n:>3} events -> {name}")

    if args.past_ics:
        try:
            past = get_past_events(radius_km=args.radius, weeks=args.past_weeks,
                                   use_cache=not args.refresh)
        except requests.RequestException as exc:
            print(f"Could not fetch past events: {exc}", file=sys.stderr)
            return 1
        past_path = calendar_feed.write(past, args.past_ics, radius_km=args.radius)
        print(f"{len(past)} past events -> {past_path}")

    if not events:
        print("No events found for those filters.")
        return 0

    for event in events:
        bits = [f"{event.city} · {event.km:.0f} km"]
        if event.time:
            bits.append(event.time)
        if event.cost:
            bits.append(event.cost)
        print(f"{event.date:%d/%m}  {event.label:<17}  {event.shop:<26}  {' · '.join(bits)}")

    path = None
    if args.no_poster:
        print(f"\n{len(events)} events (poster skipped)")
    else:
        path = render(events, args.out, radius_km=args.radius)
        print(f"\n{len(events)} events -> {path}")

    if args.ics:
        ics_path = calendar_feed.write(events, args.ics, radius_km=args.radius)
        print(f"calendar -> {ics_path}")

    if args.discord and path:
        try:
            post_to_discord(args.discord, path, len(events))
            print("Posted to Discord.")
        except requests.RequestException as exc:
            print(f"Discord post failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
