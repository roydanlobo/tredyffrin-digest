#!/usr/bin/env python3
"""
Tredyffrin Township Meeting Digest — pipeline prototype
=========================================================

Turns a Tredyffrin Township Board of Supervisors "minutes" PDF into a
short, plain-language digest entry, and rebuilds the digest HTML page
from all digests collected so far.

WHY THIS EXISTS
----------------
The hand-built prototype (tredyffrin-digest.html) was written by reading
three real minutes PDFs and summarizing them manually, to prove the
concept works. This script is the next step: the part of the pipeline
that would let a real product generate a new digest automatically every
time the township posts new minutes, instead of someone doing it by hand.

WHAT IT DOES
------------
1. Downloads a minutes PDF from tredyffrin.org (or reads one from disk).
2. Extracts the raw text.
3. Sends that text to Claude with a prompt that asks for a structured,
   plain-language digest: topic tags + a handful of highlight bullets,
   in the same voice/format as the hand-built prototype.
4. Saves the result into digest_data.json (one entry per meeting).
5. Re-renders tredyffrin-digest-generated.html from *all* entries in that
   file, so each run keeps the page up to date rather than overwriting by
   hand — including an email-subscribe box and a link to the RSS feed.
6. Re-renders feed.xml (a standard RSS 2.0 feed) from the same entries, so
   residents can subscribe with any feed reader, or so other local sites
   (Patch, aggregators) can pick it up without a bespoke integration.
7. For a genuinely new meeting (not a re-run correcting an existing one),
   creates a DRAFT email in Buttondown via their API — it does NOT send it.
   You still review the draft in your Buttondown dashboard and hit Send
   yourself, same reasoning as checking the digest against the source PDF
   before publishing it anywhere. Skipped entirely if BUTTONDOWN_API_KEY
   isn't set.

WHAT IT DOESN'T DO YET (left for a real build-out)
---------------------------------------------------
- Auto-discover new meetings on tredyffrin.org (it takes a specific PDF
  URL or file per run; a scheduler/crawler would drive this).
- Cross-meeting "storyline" detection (the Chase Road Park thread in the
  prototype was noticed and written by a human reading three meetings
  side by side — automating *that* well is a genuinely harder problem
  than single-meeting summarization, and worth treating as its own step
  rather than bolting on here).
- Multi-township support (every municipality has its own site/PDF
  layout; this script is written specifically for tredyffrin.org's
  current minutes format).

REQUIREMENTS
------------
    pip install requests pdfplumber anthropic

    export ANTHROPIC_API_KEY=sk-...

    # Optional — only needed if you want draft emails created automatically.
    # Get this from Buttondown Settings > Programming > API Key.
    export BUTTONDOWN_API_KEY=...

NOTE ON THIS SANDBOX
---------------------
Outbound requests to tredyffrin.org were blocked by this sandbox's
network proxy (confirmed via a 403 on the CONNECT tunnel), so the
download step below could not be exercised end-to-end here — the
digest content in the prototype HTML was produced by fetching the PDFs
through the assistant's own web-fetch tool instead, then hand-written
into the page. This script is written to run in a normal environment
(a laptop, a server, a scheduled job) where that restriction doesn't
apply.

USAGE
-----
    # From a URL on tredyffrin.org:
    python generate_digest.py --url "https://www.tredyffrin.org/files/.../07202026-bos-public-meeting-minutes.pdf" --date "2026-07-20"

    # From a PDF you already have on disk:
    python generate_digest.py --file ./minutes.pdf --date "2026-07-20"

    # Rebuild the HTML page from digest_data.json without adding anything new:
    python generate_digest.py --render-only
"""

import argparse
import json
import os
import sys
from pathlib import Path

DATA_FILE = Path("digest_data.json")
OUTPUT_HTML = Path("tredyffrin-digest-generated.html")
OUTPUT_RSS = Path("feed.xml")
SOURCE_LABEL = "Tredyffrin Township, Chester County, PA"

# Placeholder — once this is hosted somewhere real, set this to that page's
# actual URL. It's used as the RSS <link>/<guid> base and the channel link.
# Until then the feed is still valid, just self-referential with a placeholder.
SITE_URL = "https://roydanlobo.github.io/tredyffrin-digest/"

DIGEST_PROMPT = """You are writing a short, plain-language digest of a Tredyffrin \
Township Board of Supervisors meeting for residents who don't have time to read \
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


def download_pdf(url: str, dest: Path) -> Path:
    import requests

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def extract_text(pdf_path: Path) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def summarize_with_claude(minutes_text: str, meeting_date: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = DIGEST_PROMPT.format(date=meeting_date, text=minutes_text[:15000])

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


def load_data() -> list:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_data(entries: list) -> None:
    entries.sort(key=lambda e: e["date"], reverse=True)
    DATA_FILE.write_text(json.dumps(entries, indent=2))


def render_html(entries: list) -> None:
    """Minimal, dependency-free re-render of the digest page from JSON entries."""
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
<title>Tredyffrin Township Meeting Digest — generated</title>
<link rel="alternate" type="application/rss+xml" title="{SOURCE_LABEL} — Meeting Digest" href="feed.xml">
<style>
body{{font-family:Georgia,serif;max-width:780px;margin:2rem auto;padding:0 1.5rem;color:#232323;}}
.ui{{font-family:-apple-system,Helvetica,Arial,sans-serif;}}
article.meeting{{border:1px solid #e3ddd2;border-radius:10px;padding:1.4rem 1.6rem;margin-bottom:1.4rem;}}
.date{{font-weight:700;font-size:1.1rem;}}
.tags span{{background:#eef2ee;color:#2f6f4e;border-radius:20px;padding:.2rem .6rem;font-size:.72rem;margin-right:.3rem;}}
.subscribe{{background:#f4f1ea;border:1px solid #e3ddd2;border-radius:8px;padding:1rem 1.2rem;margin-bottom:1.6rem;}}
.subscribe form{{display:flex;flex-wrap:wrap;gap:.5rem;margin:.5rem 0;}}
.subscribe input[type=email]{{flex:1 1 220px;padding:.5rem .7rem;border-radius:6px;border:1px solid #c9c2b0;}}
.subscribe input[type=submit]{{padding:.5rem 1rem;border-radius:6px;border:none;background:#2f6f4e;color:#fff;font-weight:600;cursor:pointer;}}
.subscribe .fine{{font-size:.78rem;color:#5b5b5b;margin:0;}}
</style>
</head>
<body>
<h1>{SOURCE_LABEL} — Meeting Digest</h1>
<p class="ui">Auto-generated from official minutes. Not affiliated with the township.</p>

<!-- Same Buttondown embed pattern as the hand-built prototype — replace
     YOUR-USERNAME once a Buttondown (or other) account exists. Keep this as
     a plain HTML form post (not JS fetch) per Buttondown's docs, so
     CAPTCHA/validation-error flows still work for subscribers. -->
<div class="subscribe ui">
  <strong>Get the next digest by email.</strong>
  <form action="https://buttondown.com/api/emails/embed-subscribe/YOUR-USERNAME" method="post" class="embeddable-buttondown-form">
    <input type="email" name="email" placeholder="you@example.com" required aria-label="Email address">
    <input type="hidden" value="1" name="embed">
    <input type="submit" value="Subscribe">
  </form>
  <p class="fine">Or <a href="feed.xml">subscribe via RSS</a>. No spam, sent only when a new digest posts.</p>
</div>

{''.join(cards)}
</body>
</html>
"""
    OUTPUT_HTML.write_text(html)
    print(f"Wrote {OUTPUT_HTML} with {len(entries)} meeting(s).")


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


def render_rss(entries: list) -> None:
    """Write a standard RSS 2.0 feed so residents can subscribe with any
    feed reader, and so the digest can be picked up by aggregators (e.g.
    Patch, other local sites) without a bespoke integration per platform."""
    import html as html_lib
    from datetime import datetime, timezone, timedelta
    from email.utils import format_datetime

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
  <title>{SOURCE_LABEL} — Meeting Digest</title>
  <link>{SITE_URL}</link>
  <description>Plain-language digests of Tredyffrin Township Board of Supervisors meetings, generated from official public minutes. Unofficial, not affiliated with the township.</description>
  <language>en-us</language>
  <lastBuildDate>{build_date}</lastBuildDate>
{''.join(items)}
</channel>
</rss>
"""
    OUTPUT_RSS.write_text(rss)
    print(f"Wrote {OUTPUT_RSS} with {len(entries)} item(s).")


def create_buttondown_draft(entry: dict) -> None:
    """Create a DRAFT email in Buttondown for this digest — not sent yet.

    Deliberately creates a draft rather than sending immediately: Buttondown's
    own docs note that creating an email via the API "will instantly trigger
    sending actual emails" unless you explicitly set status to "draft". Given
    these digests are AI-generated summaries of real government minutes, a
    human should read the draft in the Buttondown dashboard and hit Send
    themselves — same reasoning as reviewing the digest against the source
    PDF before publishing it anywhere. Once you fully trust the pipeline, you
    could change status below to "about_to_send" to skip that step, but
    that's a deliberate choice to make later, not the default here.

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

    subject = f"Board of Supervisors — {entry['date']}"
    body_lines = [f"- {h}" for h in entry["highlights"]]
    body = (
        f"**{subject}**\n\n"
        + "\n".join(body_lines)
        + f"\n\n[Official minutes (PDF)]({entry['minutes_url']})\n\n"
        + f"[Read this and past digests]({SITE_URL})\n\n"
        + "---\n*Unofficial digest, not affiliated with the township. "
        + "Generated from public meeting minutes — verify anything important "
        + "against the source PDF above.*"
    )

    resp = requests.post(
        "https://api.buttondown.com/v1/emails",
        headers={"Authorization": f"Token {api_key}"},
        json={"subject": subject, "body": body, "status": "draft"},
        timeout=30,
    )
    if resp.status_code >= 300:
        print(f"Buttondown draft creation failed ({resp.status_code}): {resp.text}")
        return
    print(f"Created a DRAFT email in Buttondown for {entry['date']} — "
          f"review and send it manually from your Buttondown dashboard.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="URL of a minutes PDF on tredyffrin.org")
    parser.add_argument("--file", help="Path to a minutes PDF already on disk")
    parser.add_argument("--date", help="Meeting date, e.g. 2026-07-20 (required with --url/--file)")
    parser.add_argument("--render-only", action="store_true", help="Just rebuild the HTML from digest_data.json")
    args = parser.parse_args()

    entries = load_data()

    if args.render_only:
        render_html(entries)
        render_rss(entries)
        return

    if not args.url and not args.file:
        parser.error("Provide --url, --file, or --render-only")
    if not args.date:
        parser.error("--date is required, e.g. --date 2026-07-20")

    if args.url:
        pdf_path = Path("_downloaded_minutes.pdf")
        print(f"Downloading {args.url} ...")
        download_pdf(args.url, pdf_path)
        minutes_url = args.url
    else:
        pdf_path = Path(args.file)
        minutes_url = f"file://{pdf_path.resolve()}"

    print("Extracting text ...")
    text = extract_text(pdf_path)
    if not text:
        sys.exit("No text extracted from PDF — it may be a scanned image without OCR text.")

    print("Summarizing with Claude ...")
    digest = summarize_with_claude(text, args.date)

    entry = {
        "date": args.date,
        "minutes_url": minutes_url,
        "tags": digest["tags"],
        "highlights": digest["highlights"],
    }

    is_new_meeting = args.date not in [e["date"] for e in entries]

    entries = [e for e in entries if e["date"] != args.date]  # replace if re-run
    entries.append(entry)
    save_data(entries)
    render_html(entries)
    render_rss(entries)

    # Only draft an email for a genuinely new meeting — re-running this
    # command to fix a typo in an existing entry shouldn't create a second
    # draft for the same date.
    if is_new_meeting:
        create_buttondown_draft(entry)
    else:
        print(f"Updated existing entry for {args.date} — not creating a new "
              f"Buttondown draft (one may already exist from the first run).")


if __name__ == "__main__":
    main()
