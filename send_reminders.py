#!/usr/bin/env python3
"""One-off nudge for subscribers stuck on "Unactivated" in Buttondown.

Buttondown requires double opt-in on every signup (this is what keeps bots
and typo'd addresses off your list) — someone signs up, gets a confirmation
email, and stays "Unactivated" (no digests) until they click the link in
it. Buttondown can auto-send ONE reminder 24 hours after signup, but only
if you've turned that on in Settings > Subscribing > Reminder, and it won't
retroactively catch people who signed up before you turned it on.

This script finds everyone currently stuck as "Unactivated" (account-wide,
not per-township — Buttondown doesn't scope this by tag) and re-sends them
the confirmation email via the API, so they get another chance to confirm
without you doing it by hand per person.

Usage:
    python send_reminders.py             # actually sends the reminders
    python send_reminders.py --dry-run   # just lists who would get one

Requires BUTTONDOWN_API_KEY in the environment, same as generate_digest.py
and catchup_email.py.
"""

import argparse
import os
import sys

import requests

API_BASE = "https://api.buttondown.com/v1"


def list_unactivated(api_key: str) -> list:
    subscribers = []
    url = f"{API_BASE}/subscribers"
    params = {"type": "unactivated"}
    while url:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {api_key}"},
            params=params,
            timeout=30,
        )
        if resp.status_code >= 300:
            sys.exit(f"Failed to list subscribers ({resp.status_code}): {resp.text}")
        data = resp.json()
        subscribers.extend(data.get("results", []))
        url = data.get("next")  # already a full URL if present; params only apply to the first request
        params = None
    return subscribers


def send_reminder(api_key: str, subscriber_id: str) -> bool:
    resp = requests.post(
        f"{API_BASE}/subscribers/{subscriber_id}/send-reminder",
        headers={"Authorization": f"Token {api_key}"},
        timeout=30,
    )
    return resp.status_code < 300


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List who's unactivated without actually sending anything.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        sys.exit(
            "BUTTONDOWN_API_KEY not set — export it first, same as for "
            "generate_digest.py's draft creation."
        )

    unactivated = list_unactivated(api_key)
    if not unactivated:
        print("Nobody is currently Unactivated — nothing to do.")
        return

    print(f"Found {len(unactivated)} unactivated subscriber(s):")
    for sub in unactivated:
        print(f"  - {sub['email_address']} (signed up {sub['creation_date'][:10]})")

    if args.dry_run:
        print("\nDry run — no reminders sent. Drop --dry-run to actually send them.")
        return

    print()
    sent, failed = 0, 0
    for sub in unactivated:
        ok = send_reminder(api_key, sub["id"])
        if ok:
            print(f"  Reminder sent -> {sub['email_address']}")
            sent += 1
        else:
            print(f"  FAILED -> {sub['email_address']}")
            failed += 1

    print(f"\nDone: {sent} reminder(s) sent, {failed} failed.")
    if failed:
        print(
            "Buttondown may cap how many reminders one subscriber can get — "
            "a failure for the same person repeatedly probably means they've "
            "already hit that cap, not that something's broken."
        )


if __name__ == "__main__":
    main()
