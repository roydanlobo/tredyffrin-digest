#!/usr/bin/env python3
"""One-time catch-up email for Buttondown.

Rolls up every entry currently in a township's digest_data_<township>.json
into a single DRAFT email (not sent) — meant for a new subscriber who joins
today and would otherwise have missed everything before whatever meeting
comes next. Separate from generate_digest.py's per-meeting drafts, which
only fire for a meeting that's new as of that script run.

Usage:
    python catchup_email.py --township tredyffrin
    python catchup_email.py --township upper-merion

Requires BUTTONDOWN_API_KEY in the environment, same as generate_digest.py.
Creates a DRAFT — nothing is emailed to anyone until you open it in the
Buttondown dashboard and hit Send yourself. If BUTTONDOWN_TAG_TREDYFFRIN /
BUTTONDOWN_TAG_UPPER_MERION is set (see generate_digest.py's docstring),
the draft is targeted to just that township's tagged subscribers.
"""

import argparse
import json
import os
import sys

from generate_digest import TOWNSHIPS, SITE_ROOT, MARKDOWN_MODE_COMMENT, get_township


def build_catchup_email(entries: list, township: dict) -> tuple:
    # Oldest first, so the catch-up reads as a chronological story rather
    # than starting with "here's what just happened" and working backward.
    ordered = sorted(entries, key=lambda e: e["date"])
    label = township["short_label"]
    subject = (
        f"Catching you up: {label} Board of Supervisors, "
        f"{ordered[0]['date']} to {ordered[-1]['date']}"
    )

    # Each block below is joined with a BLANK line ("\n\n"), not a single
    # newline — Markdown needs blank lines between block-level elements
    # (headings, lists, paragraphs) to parse them as separate elements
    # rather than one run-on paragraph. Bullets within a block use a single
    # "\n", which is fine — consecutive list items don't need blank lines
    # between them.
    blocks = [
        f"You're now set up to get a plain-language digest every time "
        f"{label}'s Board of Supervisors meets. Here's everything on "
        f"record so far, so you're starting from the same place as "
        f"everyone else:"
    ]
    for e in ordered:
        # First 3 highlights per meeting keeps this scannable — full detail
        # (all highlights + the source PDF) is one click away per meeting.
        bullets = "\n".join(f"- {h}" for h in e["highlights"][:3])
        blocks.append(
            f"**{e['date']}**\n\n{bullets}\n\n"
            f"[Full digest & official minutes]({e['minutes_url']})"
        )

    site_link = SITE_ROOT + township["site_page"]
    blocks.append(f"[See every meeting, in full, on the site]({site_link})")
    # Buttondown's own subscribe-form template tag — only appears on the
    # web/archive version of the email, not the actual email sent to
    # subscribers, so it's aimed at someone this got forwarded to. No tag
    # parameter, so it won't apply the per-township tag the way the site's
    # own subscribe form does.
    blocks.append("{{ subscribe_form }}")
    blocks.append(
        "---\n\n*Unofficial digest, not affiliated with the township. "
        "Generated from public meeting minutes — verify anything important "
        "against the source PDFs linked above.*"
    )
    body = MARKDOWN_MODE_COMMENT + "\n\n".join(blocks)
    return subject, body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--township", choices=sorted(TOWNSHIPS), default="tredyffrin")
    args = parser.parse_args()
    township = get_township(args.township)

    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        sys.exit(
            "BUTTONDOWN_API_KEY not set — export it first, same as for "
            "generate_digest.py's draft creation."
        )

    data_file = township["data_file"]
    if not data_file.exists():
        sys.exit(f"{data_file} not found — run this from the project folder.")

    entries = json.loads(data_file.read_text())
    if not entries:
        sys.exit(f"{data_file} is empty — nothing to catch anyone up on yet.")

    subject, body = build_catchup_email(entries, township)

    import requests

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
              f"will be untargeted (goes to ALL subscribers) unless you set "
              f"the audience manually in Buttondown before sending.")

    resp = requests.post(
        "https://api.buttondown.com/v1/emails",
        headers={"Authorization": f"Token {api_key}"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        sys.exit(f"Buttondown draft creation failed ({resp.status_code}): {resp.text}")

    dates = sorted(e["date"] for e in entries)
    print(
        f"Created a DRAFT catch-up email in Buttondown for {township['label']} "
        f"covering {len(entries)} meeting(s) ({dates[0]} to {dates[-1]}). "
        "Review it in your dashboard (Emails > Drafts) before sending."
    )


if __name__ == "__main__":
    main()
