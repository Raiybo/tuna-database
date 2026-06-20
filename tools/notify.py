#!/usr/bin/env python3
"""Push the next day's bluefin forecast to your phone (evening heads-up).

Default channel is ntfy.sh (zero account): set NTFY_TOPIC (and optionally
NTFY_SERVER / NTFY_TOKEN). Telegram and Pushover are also supported if their
env vars are set. Writes docs/forecast.md as a snapshot.

    PYTHONPATH=src python tools/notify.py --day tomorrow
    PYTHONPATH=src python tools/notify.py --dry-run        # compose, don't send

Env:
    NTFY_TOPIC, NTFY_SERVER (default https://ntfy.sh), NTFY_TOKEN
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    PUSHOVER_TOKEN, PUSHOVER_USER
    NOTIFY_ONLY_GOOD=1   -> stay quiet unless verdict is GO/DECENT
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

from tuna import forecast as forecast_mod
from tuna.conditions import compass
from tuna.sources._http import post

VERDICT_EMOJI = {"GO": "🟢", "DECENT": "🟡", "MARGINAL": "🟠", "SLOW": "🔴", "TOUGH": "🌬️"}
VERDICT_PRIORITY = {"GO": "high", "DECENT": "default", "MARGINAL": "low",
                    "SLOW": "low", "TOUGH": "low"}
VERDICT_TAGS = {"GO": "fish,white_check_mark", "DECENT": "fish",
                "MARGINAL": "fish", "SLOW": "fish", "TOUGH": "fish,wind_blowing_face"}


def pick_day(fc, which: str):
    if not fc.days:
        return None
    if which == "best":
        return max(fc.days, key=lambda d: d.score)
    if which == "today":
        return next((d for d in fc.days if d.is_today), fc.days[0])
    # tomorrow: the day after today's
    for i, d in enumerate(fc.days):
        if d.is_today and i + 1 < len(fc.days):
            return fc.days[i + 1]
    return fc.days[1] if len(fc.days) > 1 else fc.days[0]


def compose(fc, day):
    em = VERDICT_EMOJI.get(day.verdict, "")
    when = "Today" if day.is_today else f"{day.weekday} {day.date[5:]}"
    title = f"{when}: {day.verdict} - bluefin peak {day.peak_window}".encode("ascii", "ignore").decode()
    why = " · ".join(p.name for p in day.patterns[:3]) or "no strong pattern"
    wind = (f"{day.wind_min:.0f}-{day.wind_max:.0f} km/h {compass(day.wind_dir)}"
            if day.wind_min is not None else "n/a")
    body = (
        f"{when} · {day.verdict} {em}  (confidence {day.confidence})\n"
        f"Peak bite {day.peak_hour}  (window {day.peak_window})\n"
        f"Best: {day.best_spot.name}, {day.best_dist_nm:.1f} nm {day.best_heading} "
        f"from {fc.home.name}\n"
        f"SST {day.sst}°C · wind {wind} · swell "
        f"{day.wave_max if day.wave_max is not None else 'n/a'} m\n"
        f"Moon {day.moon['phase']} {day.moon['illumination_pct']}% · "
        f"majors {' / '.join(day.moon['major_periods'])}\n"
        f"Why: {why}"
    )
    return title, body, VERDICT_PRIORITY.get(day.verdict, "default"), VERDICT_TAGS.get(day.verdict, "fish")


def send_ntfy(title, body, priority, tags):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return None
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": priority, "Tags": tags}
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, _ = post(f"{server}/{topic}", body.encode("utf-8"), headers)
    return f"ntfy:{status}"


def send_telegram(title, body):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return None
    data = urllib.parse.urlencode({"chat_id": chat, "text": f"{title}\n\n{body}"}).encode()
    status, _ = post(f"https://api.telegram.org/bot{tok}/sendMessage", data,
                     {"Content-Type": "application/x-www-form-urlencoded"})
    return f"telegram:{status}"


def send_pushover(title, body, priority):
    tok, user = os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")
    if not (tok and user):
        return None
    prio = "1" if priority == "high" else "0"
    data = urllib.parse.urlencode({"token": tok, "user": user, "title": title,
                                   "message": body, "priority": prio}).encode()
    status, _ = post("https://api.pushover.net/1/messages.json", data,
                     {"Content-Type": "application/x-www-form-urlencoded"})
    return f"pushover:{status}"


def write_snapshot(fc, day):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lines = [f"# Tuna forecast - from {fc.home.name}", "",
             "| Day | Verdict | Score | Peak window | Best spot | Conf |",
             "|---|---|--:|---|---|---|"]
    for d in fc.days:
        tag = "Today" if d.is_today else f"{d.weekday} {d.date[5:]}"
        lines.append(f"| {tag} | {d.verdict} | {d.score:.2f} | {d.peak_window} | "
                     f"{d.best_spot.name} {d.best_dist_nm:.0f}nm {d.best_heading} | {d.confidence} |")
    if day:
        lines += ["", f"**Heads-up ({'Today' if day.is_today else day.weekday + ' ' + day.date}):** "
                  f"{day.verdict} - peak {day.peak_window} at {day.best_spot.name}. "
                  f"Patterns: {', '.join(p.name for p in day.patterns) or 'none'}."]
    path = os.path.join(root, "docs", "forecast.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Push the bluefin forecast to your phone.")
    p.add_argument("--day", choices=("tomorrow", "today", "best"), default="tomorrow")
    p.add_argument("--days", type=int, default=None, help="forecast horizon")
    p.add_argument("--dry-run", action="store_true", help="compose & print, do not send")
    args = p.parse_args(argv)

    fc = forecast_mod.build_forecast(days=args.days)
    day = pick_day(fc, args.day)
    if not day:
        print("No forecast available; nothing to send.", file=sys.stderr)
        return 1

    title, body, priority, tags = compose(fc, day)
    snap = write_snapshot(fc, day)
    print(f"--- {title} ---\n{body}\n(snapshot: {snap})")

    if os.environ.get("NOTIFY_ONLY_GOOD") and day.verdict not in ("GO", "DECENT"):
        print(f"NOTIFY_ONLY_GOOD set and verdict is {day.verdict}; staying quiet.")
        return 0

    if args.dry_run:
        print("dry-run: not sending.")
        return 0

    results = [r for r in (send_ntfy(title, body, priority, tags),
                           send_telegram(title, body),
                           send_pushover(title, body, priority)) if r]
    if not results:
        print("No notification channel configured (set NTFY_TOPIC). Snapshot written.",
              file=sys.stderr)
        return 0
    print("sent ->", ", ".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
