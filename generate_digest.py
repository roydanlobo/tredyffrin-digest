#!/usr/bin/env python3
"""
Chester County Meeting Digest — pipeline (multi-township)
=========================================================

Turns a township Board of Supervisors "minutes" PDF into a short,
plain-language digest entry, and rebuilds that township's RSS feed and a
generic HTML page from all digests collected so far.

Started as a Tredyffrin-only prototype; now supports multiple townships,
each with its own data file, RSS feed, and (optionally) its own Buttondown
subscriber tag — see TOWNSHIPS below. Every township needs its own
site-specific logic for finding a minutes URL (every municipality's site is
laid out differently), but everything downstream — extract, summarize,
save, render, draft — is shared.

WHAT IT DOES
------------
1. Downloads a minutes PDF (or reads one from disk).
2. Extracts the raw text.
3. Sends that text to Claude with a prompt that asks for a structured,
   plain-language digest: topic tags + a handful of highlight bullets.
4. Saves the result into that township's digest_data_<township>.json (one
   entry per meeting).
5. Re-renders a generic HTML page and that township's RSS feed from *all*
   entries in that file. (The real, hand-styled site pages — index.html for
   Tredyffrin, upper-merion.html for Upper Merion — are still updated by
   hand; merging that into this render step is on the to-do list, same as
   it was before multi-township support.)
6. For a genuinely new meeting (not a re-run correcting an existing one),
   creates a DRAFT email in Buttondown via their API — it does NOT send it.
   You still review the draft in your Buttondown dashboard and hit Send
   yourself. Skipped entirely if BUTTONDOWN_API_KEY isn't set.

WHAT IT DOESN'T DO YET (left for a real build-out)
---------------------------------------------------
- Auto-discover new meetings on a township's site (it takes a specific PDF
  URL or file per run; a scheduler/crawler would drive this).
- Cross-meeting "storyline" detection (e.g. the Chase Road Park thread) is
  still a human-reads-multiple-meetings job.
- A find_minutes_url() helper per township that turns "give me the URL for
  the Sept 21 meeting" into the actual PDF link automatically — right now
  you find that URL yourself (or ask the assistant) and pass it via --url.

REQUIREMENTS
------------
    pip install requests pdfplumber anthropic playwright
    playwright install chromium

    export ANTHROPIC_API_KEY=sk-...

    # Optional — only needed if you want draft emails created automatically.
    # Get this from Buttondown Settings > Programming > API Key.
    export BUTTONDOWN_API_KEY=...

    # Optional — only needed if you're using one Buttondown newsletter with
    # per-township tags (see README) rather than emailing every subscriber
    # every digest. Get tag IDs from Buttondown's Tags dashboard, or
    # `GET /v1/tags`. If unset for a township, drafts for that township go
    # out untargeted (i.e. to everyone) — you'll get a warning printed.
    export BUTTONDOWN_TAG_TREDYFFRIN=sub_tag_...
    export BUTTONDOWN_TAG_UPPER_MERION=sub_tag_...

NOTE ON BOT PROTECTION
-----------------------
tredyffrin.org sits behind a WAF that blocks plain HTTP clients (like
`requests`, even with full browser-matching headers) but allows real
browsers through — pointing to TLS/behavioral fingerprinting rather than
a simple header check. download_pdf() below uses a headless Chromium
browser (via Playwright) instead of `requests` specifically to get past
this — the same approach should work for any other township's site, since
it isn't Tredyffrin-specific, but it hasn't been proven yet against
umtownship.org (Upper Merion). If a township's site turns out to block
even Playwright, --file (a manually-downloaded copy) is the fallback.

USAGE
-----
    # From a URL on the township's site:
    python generate_digest.py --township tredyffrin --url "https://www.tredyffrin.org/files/.../07202026-bos-public-meeting-minutes.pdf" --date "2026-07-20"
    python generate_digest.py --township upper-merion --url "https://www.umtownship.org/AgendaCenter/ViewFile/Minutes/_03122026-438" --date "2026-03-12"

    # From a PDF you already have on disk:
    python generate_digest.py --township tredyffrin --file ./minutes.pdf --date "2026-07-20"

    # Rebuild the RSS/generic HTML from digest_data_<township>.json without adding anything new:
    python generate_digest.py --township tredyffrin --render-only

--township defaults to "tredyffrin" if omitted, so old commands from before
multi-township support still work unchanged.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Per-township configuration. Add a new dict entry here to support another
# municipality — everything else in this file reads from it rather than
# hardcoding Tredyffrin specifics.
# ---------------------------------------------------------------------------
TOWNSHIPS = {
    "tredyffrin": {
        "label": "Tredyffrin Township, Chester County, PA",
        "short_label": "Tredyffrin Township",
        "homepage": "https://www.tredyffrin.org/",
        "data_file": Path("digest_data_tredyffrin.json"),
        "rss_file": Path("feed-tredyffrin.xml"),
        "generic_html_file": Path("tredyffrin-digest-generated.html"),
        # The hand-styled page people actually visit, relative to SITE_ROOT.
        "site_page": "index.html",
        "video_url": "https://www.tredyffrin.org/Departments/Communications/Tredyffrin-Township-TV",
        "buttondown_tag_env": "BUTTONDOWN_TAG_TREDYFFRIN",
    },
    "upper-merion": {
        "label": "Upper Merion Township, Montgomery County, PA",
        "short_label": "Upper Merion Township",
        "homepage": "https://www.umtownship.org/",
        "data_file": Path("digest_data_upper-merion.json"),
        "rss_file": Path("feed-upper-merion.xml"),
        "generic_html_file": Path("upper-merion-digest-generated.html"),
        "site_page": "upper-merion.html",
        "video_url": "https://vimeo.com/channels/umtbos",
        "buttondown_tag_env": "BUTTONDOWN_TAG_UPPER_MERION",
    },
}

# Once this is hosted somewhere real, set this to that root URL. Used to
# build each township's page link for RSS <link>/<guid> and Buttondown
# drafts. Until then feeds are still valid, just self-referential.
SITE_ROOT = "https://digest.platformlens.net/"

# Buttondown "attempts to intelligently detect the format of the body
# automatically" (Markdown vs HTML vs plain text) and can guess wrong —
# confirmed in practice: a draft came through with **bold**, - bullets, and
# [links](url) all showing up as literal characters, unrendered, because it
# was auto-detected as plain/"naked" text instead of Markdown. Prepending
# this comment forces Markdown parsing explicitly rather than relying on
# the guess. Must be followed by a blank line.
MARKDOWN_MODE_COMMENT = "<!-- buttondown-editor-mode: markdown -->\n\n"

DIGEST_PROMPT = """You are writing a short, plain-language digest of a {township} \
Board of Supervisors meeting for residents who don't have time to read \
the full minutes or watch the video. You will be given the raw text of the \
official meeting minutes.

Write your response as JSON with this exact shape, and nothing else:

{{
  "tags": ["2-4 short topic tags, e.g. 'Parks & Recreation', 'Infrastructure', 'Public Safety', 'Finance', 'Governance'"],
  "highlights": [
    "4-7 bullet points, each starting with a short bold-style lead phrase then a plain-English sentence. Include specific numbers (dollar amounts, vote counts) exactly as they appear in the source. Do not invent or round any figures. If residents raised concerns or pushed back on something, say so plainly and name who/what if given.",
    "..."
  ]
}}

Only use information present in the source text below. Do not speculate about \
anything not stated. Keep each highlight to one or two sentences.

MEETING DATE: {date}

SOURCE MINUTES TEXT:
{text}
"""


def get_township(slug: str) -> dict:
    try:
        return TOWNSHIPS[slug]
    except KeyError:
        sys.exit(f"Unknown township '{slug}'. Choices: {', '.join(TOWNSHIPS)}")


def download_pdf(url: str, dest: Path, homepage: str) -> Path:
    """Download a minutes/agenda PDF using a real headless browser.

    EARLIER APPROACH (kept here as a comment for the record): a `requests`
    session with full browser-matching headers and a homepage visit first to
    pick up any anti-bot cookie. That still got a 403 on a tredyffrin.org URL
    confirmed to load fine in an actual browser — which rules out "missing
    header" as the cause. The remaining explanation is TLS/behavioral
    fingerprinting: the WAF is looking at signals below the HTTP header
    layer (the TLS ClientHello's cipher order/extensions, aka a JA3
    fingerprint) that `requests`' underlying urllib3/OpenSSL stack can't
    match a real browser's, no matter what headers you set on top of it.

    THE FIX: use an actual headless browser (Playwright + Chromium) to fetch
    the file. Since it's a real browser engine, its TLS fingerprint and
    request behavior are indistinguishable from a person clicking the link
    manually.

    Requires:
        pip install playwright
        playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "download_pdf() needs Playwright to get past bot protection. "
            "Install it with:\n"
            "    pip install playwright\n"
            "    playwright install chromium"
        )

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(user_agent=user_agent)
            # Visit the homepage first in a real page — same reasoning as
            # the old session.get() warm-up, but this time it's a real
            # navigation (cookies, JS challenges if any get resolved
            # normally) rather than a bare HTTP request pretending to be one.
            page = context.new_page()
            page.goto(homepage, wait_until="domcontentloaded")
            page.close()

            # Fetch the actual PDF through the same browser context, so it
            # carries whatever cookies/session state the homepage visit set.
            response = context.request.get(url, headers={"Referer": homepage})
            if not response.ok:
                sys.exit(
                    f"Download failed: HTTP {response.status} for {url}\n"
                    "If you've confirmed this URL loads in your own browser, "
                    "the site may have its own bot-protection quirks — the "
                    "manual-download workaround (--file) still works as a "
                    "fallback."
                )
            dest.write_bytes(response.body())
        finally:
            browser.close()
    return dest


def extract_text(pdf_path: Path) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def summarize_with_claude(minutes_text: str, meeting_date: str, township_label: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = DIGEST_PROMPT.format(
        township=township_label, date=meeting_date, text=minutes_text[:15000]
    )

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Be tolerant of the model wrapping JSON in a code fence.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def load_data(data_file: Path) -> list:
    if data_file.exists():
        return json.loads(data_file.read_text())
    return []


def save_data(entries: list, data_file: Path) -> None:
    entries.sort(key=lambda e: e["date"], reverse=True)
    data_file.write_text(json.dumps(entries, indent=2))


def render_html(entries: list, township: dict) -> None:
    """Minimal, dependency-free re-render of a generic digest page from JSON
    entries. NOT the real site page (see module docstring) — just a
    same-data fallback/diagnostic view."""
    label = township["label"]
    rss_file = township["rss_file"].name
    cards = []
    for e in entries:
        tags_html = "".join(f"<span>{t}</span>" for t in e["tags"])
        bullets_html = "".join(f"<li>{h}</li>" for h in e["highlights"])
        cards.append(f"""
  <article class="meeting">
    <div class="meta">
      <div class="date">{e['date']}</div>
      <div class="links ui">
        <a href="{e['minutes_url']}" target="_blank" rel="noopener">Official minutes (PDF)</a>
      </div>
    </div>
    <div class="tags">{tags_html}</div>
    <ul class="highlights">{bullets_html}</ul>
  </article>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{label} — Meeting Digest — generated</title>
<link rel="alternate" type="application/rss+xml" title="{label} — Meeting Digest" href="{rss_file}">
<style>
body{{font-family:Georgia,serif;max-width:780px;margin:2rem auto;padding:0 1.5rem;color:#232323;}}
.ui{{font-family:-apple-system,Helvetica,Arial,sans-serif;}}
article.meeting{{border:1px solid #e3ddd2;border-radius:10px;padding:1.4rem 1.6rem;margin-bottom:1.4rem;}}
.date{{font-weight:700;font-size:1.1rem;}}
.tags span{{background:#eef2ee;color:#2f6f4e;border-radius:20px;padding:.2rem .6rem;font-size:.72rem;margin-right:.3rem;}}
</style>
</head>
<body>
<h1>{label} — Meeting Digest</h1>
<p class="ui">Auto-generated from official minutes. Not affiliated with the township. This is a generic diagnostic view — the real site page is {township['site_page']}.</p>

{''.join(cards) if cards else '<p class="ui">No meetings summarized yet.</p>'}
</body>
</html>
"""
    out_file = township["generic_html_file"]
    out_file.write_text(html)
    print(f"Wrote {out_file} with {len(entries)} meeting(s).")


def _rfc822_date(date_str: str) -> str:
    """Turn 'YYYY-MM-DD' into an RFC 822 date for RSS, assuming a 7pm ET
    meeting start. This uses a fixed EDT (-0400) offset year-round as a
    simplification — swap in zoneinfo('America/New_York') for a real
    build if winter (EST, -0500) meetings need to be exact."""
    from datetime import datetime, timezone, timedelta
    from email.utils import format_datetime

    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=19, minute=0, tzinfo=timezone(timedelta(hours=-4))
    )
    return format_datetime(dt)


def render_rss(entries: list, township: dict) -> None:
    """Write a standard RSS 2.0 feed so residents can subscribe with any
    feed reader, and so the digest can be picked up by aggregators (e.g.
    Patch, other local sites) without a bespoke integration per platform.
    One feed per township, so subscribing to Upper Merion's feed never pulls
    in Tredyffrin items or vice versa."""
    import html as html_lib
    from datetime import datetime, timezone, timedelta
    from email.utils import format_datetime

    label = township["label"]
    site_link = SITE_ROOT + township["site_page"]

    items = []
    for e in entries:
        title = f"Board of Supervisors — {e['date']}"
        desc_html = "<ul>" + "".join(f"<li>{h}</li>" for h in e["highlights"]) + "</ul>"
        items.append(f"""
  <item>
    <title>{html_lib.escape(title)}</title>
    <link>{html_lib.escape(e['minutes_url'])}</link>
    <guid isPermaLink="false">{html_lib.escape(e['minutes_url'])}</guid>
    <pubDate>{_rfc822_date(e['date'])}</pubDate>
    <description>{html_lib.escape(desc_html)}</description>
  </item>""")

    build_date = format_datetime(datetime.now(timezone(timedelta(hours=-4))))
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{label} — Meeting Digest</title>
  <link>{site_link}</link>
  <description>Plain-language digests of {label} Board of Supervisors meetings, generated from official public minutes. Unofficial, not affiliated with the township.</description>
  <language>en-us</language>
  <lastBuildDate>{build_date}</lastBuildDate>
{''.join(items)}
</channel>
</rss>
"""
    out_file = township["rss_file"]
    out_file.write_text(rss)
    print(f"Wrote {out_file} with {len(entries)} item(s).")


def create_buttondown_draft(entry: dict, township: dict) -> None:
    """Create a DRAFT email in Buttondown for this digest — not sent yet.

    Deliberately creates a draft rather than sending immediately: Buttondown's
    own docs note that creating an email via the API "will instantly trigger
    sending actual emails" unless you explicitly set status to "draft". Given
    these digests are AI-generated summaries of real government minutes, a
    human should read the draft in the Buttondown dashboard and hit Send
    themselves.

    If a Buttondown tag ID is configured for this township (see the
    BUTTONDOWN_TAG_* env vars in the module docstring), the draft is filtered
    to only that tag's subscribers — so a Tredyffrin digest doesn't land in
    an Upper Merion-only subscriber's inbox. If no tag ID is set, the draft
    goes out untargeted (i.e. to every subscriber on the newsletter) and a
    warning is printed, so you don't accidentally cross-post without
    noticing.

    Requires a BUTTONDOWN_API_KEY environment variable (from Buttondown's
    Settings > Programming). Silently skipped if that's not set, so the rest
    of the pipeline still works for anyone who hasn't wired this up yet.
    """
    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        print("BUTTONDOWN_API_KEY not set — skipping draft creation. "
              "Set it (Buttondown Settings > Programming) to auto-draft emails.")
        return

    import requests

    site_link = SITE_ROOT + township["site_page"]
    subject = f"{township['short_label']} — Board of Supervisors — {entry['date']}"
    body_lines = [f"- {h}" for h in entry["highlights"]]
    body = (
        MARKDOWN_MODE_COMMENT
        + f"**{subject}**\n\n"
        + "\n".join(body_lines)
        + f"\n\n[Official minutes (PDF)]({entry['minutes_url']})\n\n"
        + f"[Read this and past digests]({site_link})\n\n"
        # Buttondown's own subscribe-form template tag — per their docs it
        # only appears on the web/archive version of the email, not in the
        # actual email sent to subscribers, so this is aimed at someone who
        # got this forwarded to them rather than existing subscribers. It
        # doesn't accept a tag parameter, so anyone signing up through it
        # here won't get the per-township tag the way signing up on the
        # site does — worth mentioning if that gap matters to you.
        + "{{ subscribe_form }}\n\n"
        + "---\n\n*Unofficial digest, not affiliated with the township. "
        + "Generated from public meeting minutes — verify anything important "
        + "against the source PDF above.*"
    )

    payload = {"subject": subject, "body": body, "status": "draft"}

    tag_id = os.environ.get(township["buttondown_tag_env"])
    if tag_id:
        payload["filters"] = {
            "predicate": "and",
            "groups": [],
            "filters": [
                {"field": "subscriber.tags", "operator": "contains", "value": tag_id}
            ],
        }
    else:
        print(f"NOTE: {township['buttondown_tag_env']} is not set — this draft "
              f"will be untargeted (goes to ALL subscribers, not just "
              f"{township['short_label']} ones) unless you set the audience "
              f"manually in Buttondown before sending.")

    resp = requests.post(
        "https://api.buttondown.com/v1/emails",
        headers={"Authorization": f"Token {api_key}"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"Buttondown draft creation failed ({resp.status_code}): {resp.text}")
        return
    print(f"Created a DRAFT email in Buttondown for {township['short_label']} — "
          f"{entry['date']} — review and send it manually from your Buttondown "
          f"dashboard.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--township", choices=sorted(TOWNSHIPS), default="tredyffrin",
                         help="Which township this run is for (default: tredyffrin)")
    parser.add_argument("--url", help="URL of a minutes PDF on the township's site")
    parser.add_argument("--file", help="Path to a minutes PDF already on disk")
    parser.add_argument("--date", help="Meeting date, e.g. 2026-07-20 (required with --url/--file)")
    parser.add_argument("--render-only", action="store_true", help="Just rebuild the RSS/generic HTML from the data file")
    args = parser.parse_args()

    township = get_township(args.township)
    data_file = township["data_file"]

    entries = load_data(data_file)

    if args.render_only:
        render_html(entries, township)
        render_rss(entries, township)
        return

    if not args.url and not args.file:
        parser.error("Provide --url, --file, or --render-only")
    if not args.date:
        parser.error("--date is required, e.g. --date 2026-07-20")

    if args.url:
        pdf_path = Path("_downloaded_minutes.pdf")
        print(f"Downloading {args.url} ...")
        download_pdf(args.url, pdf_path, township["homepage"])
        minutes_url = args.url
    else:
        pdf_path = Path(args.file)
        minutes_url = f"file://{pdf_path.resolve()}"

    print("Extracting text ...")
    text = extract_text(pdf_path)
    if not text:
        sys.exit("No text extracted from PDF — it may be a scanned image without OCR text.")

    print("Summarizing with Claude ...")
    digest = summarize_with_claude(text, args.date, township["label"])

    entry = {
        "date": args.date,
        "minutes_url": minutes_url,
        "tags": digest["tags"],
        "highlights": digest["highlights"],
    }

    is_new_meeting = args.date not in [e["date"] for e in entries]

    entries = [e for e in entries if e["date"] != args.date]  # replace if re-run
    entries.append(entry)
    save_data(entries, data_file)
    render_html(entries, township)
    render_rss(entries, township)

    # Only draft an email for a genuinely new meeting — re-running this
    # command to fix a typo in an existing entry shouldn't create a second
    # draft for the same date.
    if is_new_meeting:
        create_buttondown_draft(entry, township)
    else:
        print(f"Updated existing entry for {args.date} — not creating a new "
              f"Buttondown draft (one may already exist from the first run).")


if __name__ == "__main__":
    main()
