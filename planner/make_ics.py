#!/usr/bin/env python3
"""从清单.json 生成带闹钟的 .ics（手机日历声音+文字通知）。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def ics_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def local_to_utc(date_s: str, time_s: str) -> datetime:
    # Asia/Shanghai = UTC+8, no DST
    local = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
    return local - timedelta(hours=8)


def build_ics(items: list[dict], calendar_name: str = "日次提醒") -> str:
    now = datetime.utcnow()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Rici//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
    ]
    for it in items:
        if not it.get("remindDate") or not it.get("remindTime"):
            continue
        start = local_to_utc(it["remindDate"], it["remindTime"])
        end = start + timedelta(minutes=30)
        title = it.get("title") or "提醒"
        cat = it.get("category") or ""
        summary = f"[{cat}] {title}" if cat else title
        uid = f"{it.get('id', 'item')}@rici"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp(now)}",
            f"DTSTART:{stamp(start)}",
            f"DTEND:{stamp(end)}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(it.get('notes') or title)}",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{ics_escape(summary)}",
            "TRIGGER:PT0S",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-phone", action="store_true", help="仅导出 phoneCalendar=true 的项")
    ap.add_argument("--ids", nargs="*", help="指定条目 id")
    ap.add_argument("-o", "--output", default="reminders.ics")
    args = ap.parse_args()

    data = json.loads(Path(__file__).with_name("清单.json").read_text(encoding="utf-8"))
    items = data.get("items") or []
    if args.ids:
        idset = set(args.ids)
        items = [x for x in items if x.get("id") in idset]
    elif args.all_phone:
        items = [x for x in items if x.get("phoneCalendar") is True]
    else:
        items = [x for x in items if x.get("remindDate") and x.get("remindTime")]

    text = build_ics(items)
    out = Path(args.output)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(items)} events)")


if __name__ == "__main__":
    main()
