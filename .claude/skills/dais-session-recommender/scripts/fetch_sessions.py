#!/usr/bin/env python3
"""Fetch all DAIS sessions from the official agenda page.

The agenda page embeds the full sessions list as a JSON array inside the
Drupal drupal-settings-json, so a single HTTP request pulls every session
even though the UI paginates client-side.

Output modes:
  --format full   : raw JSON of all sessions (all fields). Big (~500KB).
  --format slim   : slim JSON with title/speakers/track/industry/category/
                    level/duration/url + short body excerpt. Ideal for
                    Claude to reason over.
  --format table  : pipe-delimited table for eyeballing.

Claude-side usage:
  1. Run `fetch_sessions.py --format slim` → get JSON.
  2. Claude reads it, applies judgment (scoring, priority, why-recommend
     reasoning) based on the user's use case, and responds in the chat.
  3. The Python script deliberately does NO scoring/ranking — leave that
     to Claude so edge cases and nuance are handled.
"""
import argparse
import datetime as _dt
import html as html_mod
import json
import re
import sys
import urllib.request


DEFAULT_URL = "https://www.databricks.com/dataaisummit/agenda"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_sessions(html: str) -> list:
    marker = '"sessions":['
    idx = html.find(marker)
    if idx < 0:
        raise RuntimeError(
            'sessions JSON not found. The page structure may have changed; '
            'fall back to paginated WebFetch of agenda?page=N.'
        )
    start = idx + len('"sessions":')
    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(html):
        c = html[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"' and not esc:
            in_str = not in_str
        elif not in_str:
            if c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return json.loads(html[start : i + 1])


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def slim(s: dict, body_chars: int = 600, drop_body: bool = False) -> dict:
    cats = s.get("categories", {}) or {}
    out = {
        "title": s.get("title"),
        "speakers": [
            {
                "name": sp.get("name"),
                "role": sp.get("job_title"),
                "company": sp.get("company"),
            }
            for sp in (s.get("speakers") or [])
        ],
        "type": (cats.get("type") or [None])[0],
        "track": (cats.get("track") or [None])[0],
        "industry": cats.get("industry") or [],
        "category": cats.get("category") or [],
        "level": (cats.get("level") or [None])[0],
        "areas": cats.get("areasofinterest") or [],
        "duration_min": s.get("duration"),
        "url": f"https://www.databricks.com{s['alias']}" if s.get("alias") else None,
    }
    if not drop_body:
        body = strip_html(s.get("body") or "")
        if body_chars and len(body) > body_chars:
            body = body[:body_chars].rsplit(" ", 1)[0] + "…"
        out["body"] = body
    return out


def to_table(slim_sessions: list) -> str:
    rows = ["title | speakers | track | industry | category | level | url"]
    rows.append("---|---|---|---|---|---|---")
    for s in slim_sessions:
        sp = "; ".join(
            f"{x['name']} ({x['company']})" for x in (s.get("speakers") or []) if x.get("name")
        )
        rows.append(
            " | ".join(
                [
                    (s.get("title") or "").replace("|", "\\|"),
                    sp.replace("|", "\\|"),
                    s.get("track") or "",
                    ", ".join(s.get("industry") or []),
                    ", ".join(s.get("category") or []),
                    s.get("level") or "",
                    s.get("url") or "",
                ]
            )
        )
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument(
        "--format",
        choices=["full", "slim", "table", "jsonl"],
        default="slim",
        help="Output format (default: slim). 'jsonl' emits one slim "
        "session JSON per line, prefixed by an optional metadata header line "
        "with --with-metadata. Designed for the Read tool to ingest line-by-line.",
    )
    ap.add_argument(
        "--body-chars",
        type=int,
        default=600,
        help="Max chars of body to keep in slim/table mode (0 = unlimited)",
    )
    ap.add_argument(
        "--no-body",
        action="store_true",
        help="Drop the body field entirely (slim mode). Useful for an index "
        "file small enough to be returned by WebFetch verbatim.",
    )
    ap.add_argument(
        "--compact",
        action="store_true",
        help="Emit minified JSON (no indent, compact separators).",
    )
    ap.add_argument("--output", default="-", help="Output file or '-' for stdout")
    ap.add_argument(
        "--with-metadata",
        action="store_true",
        help="Wrap JSON output as {generated_at, source_url, session_count, sessions: [...]}",
    )
    args = ap.parse_args()

    html = fetch_html(args.url)
    sessions = extract_sessions(html)
    sys.stderr.write(f"Fetched {len(sessions)} sessions from {args.url}\n")

    def wrap(payload):
        return {
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "source_url": args.url,
            "session_count": len(sessions),
            "sessions": payload,
        }

    dump_kwargs = (
        {"separators": (",", ":")}
        if args.compact
        else {"indent": 2}
    )

    if args.format == "full":
        payload = wrap(sessions) if args.with_metadata else sessions
        data = json.dumps(payload, ensure_ascii=False, **dump_kwargs)
    elif args.format == "slim":
        slim_list = [slim(s, args.body_chars, drop_body=args.no_body) for s in sessions]
        payload = wrap(slim_list) if args.with_metadata else slim_list
        data = json.dumps(payload, ensure_ascii=False, **dump_kwargs)
    elif args.format == "jsonl":
        slim_list = [slim(s, args.body_chars, drop_body=args.no_body) for s in sessions]
        lines = []
        if args.with_metadata:
            header = {
                "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "source_url": args.url,
                "session_count": len(sessions),
                "_format": "jsonl",
                "_note": "First line is metadata. Subsequent lines: one slim session per line.",
            }
            lines.append(json.dumps(header, ensure_ascii=False, separators=(",", ":")))
        for s in slim_list:
            lines.append(json.dumps(s, ensure_ascii=False, separators=(",", ":")))
        data = "\n".join(lines) + "\n"
    else:  # table
        slim_list = [slim(s, args.body_chars, drop_body=args.no_body) for s in sessions]
        data = to_table(slim_list)

    if args.output == "-":
        sys.stdout.write(data)
    else:
        import os as _os
        out_dir = _os.path.dirname(_os.path.abspath(args.output))
        if out_dir:
            _os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(data)
        sys.stderr.write(f"Wrote {args.output}\n")


if __name__ == "__main__":
    main()
