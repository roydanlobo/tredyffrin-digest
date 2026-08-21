# Tredyffrin Meeting Digest

Plain-language digests of Tredyffrin Township Board of Supervisors meetings,
generated from the township's official public meeting minutes — so residents
don't have to read a dense PDF or watch a multi-hour video to know what got
decided.

**Status:** live prototype, 7 real meetings summarized (February–July 2026),
validated with a positive Nextdoor/Patch interest poll. Published at
https://roydanlobo.github.io/tredyffrin-digest/.

## What's here

- `index.html` — the digest page itself (open directly in a browser, no
  server needed).
- `feed.xml` — an RSS 2.0 feed of the same digests.
- `digest_data.json` — the underlying data (date, tags, highlights, source
  URL) for every meeting summarized so far. This is the source of truth;
  the HTML and RSS are both rendered from it.
- `generate_digest.py` — the pipeline: given a minutes PDF (URL or local
  file) and a meeting date, it extracts the text, asks Claude to write a
  plain-language digest (tags + highlight bullets) in the same format as
  the existing entries, appends it to `digest_data.json`, and re-renders
  both `index.html`-equivalent output and `feed.xml`.

  Note: the script currently renders to `tredyffrin-digest-generated.html`
  using a simpler template than the hand-styled `index.html` — merging
  those two (so a script run updates the real page directly) is on the
  to-do list below.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # one-time browser download, see note below
cp .env.example .env            # then fill in your real Anthropic API key
```

The script reads `ANTHROPIC_API_KEY` (and optionally `BUTTONDOWN_API_KEY`)
from the environment. Either export it in your shell, or use a tool like
`python-dotenv` to load `.env` automatically (not wired in yet — currently
you'd `export ANTHROPIC_API_KEY=sk-...` before running the script, or
source `.env` manually). Environment variables set with `$env:VAR = "..."`
in PowerShell only last for that terminal session — use the System
Environment Variables GUI if you want them to persist.

### Why Playwright?

tredyffrin.org blocks plain HTTP downloads (Python's `requests`, even with
full browser-matching headers) but allows real browsers through — this
looks like TLS/behavioral fingerprinting rather than a simple header check,
since a confirmed-real URL that loads fine by hand still 403'd from
`requests`. `download_pdf()` now drives a real headless Chromium browser via
Playwright instead, which gets past it because it *is* a real browser as
far as the site can tell. If tredyffrin.org changes its protection again,
`--file` (pointing at a manually-downloaded copy) is the fallback.

## Usage — after a new meeting posts minutes

1. Check tredyffrin.org for the new minutes PDF once it's posted (usually a
   few weeks after the meeting itself — minutes are typically approved at
   the following meeting before being published).
2. Run the script:

   ```bash
   python generate_digest.py --url "<minutes-pdf-url>" --date "2026-09-08"
   ```

3. **Read the output against the source PDF before publishing anything.**
   These digests state facts about local government — dollar amounts, vote
   counts, who said what — and an AI summary of a scanned PDF can misread a
   number. A quick check is cheap insurance.
4. Open the regenerated page locally to confirm it looks right.

To just rebuild the HTML/RSS from existing data without adding a new
meeting: `python generate_digest.py --render-only`.

### Note on the February–April 2026 entries

Those four meetings were backfilled directly (not run through this script
locally) — the assistant found the minutes URLs and extracted/summarized
their content via its own web-fetch tooling, then added the entries to
`digest_data.json` and `index.html` by hand, in the same format the script
produces. That's a reasonable one-time way to seed history, but it means
those four entries haven't been through the exact same pipeline as the
May–July ones. Worth a spot-check against the source PDFs (linked on each
entry) before treating them as fully verified, same as any other digest.

## How this idea was validated

- Chester County townships post official minutes as PDFs — public record,
  no platform terms-of-service issues. Confirmed the minutes have real
  substance (supervisor rationale, resident comments), not just terse
  motion records.
- YouTube's caption-download API requires video-owner permission, so a
  third party can't pull transcripts that way — PDFs are the right primary
  source, video links are just for "watch it yourself."
- Existing "AI meeting minutes" products (BoardBreeze, ClerkMinutes, HeyGov)
  are sold *to* the township clerk to help write minutes, not built for
  residents. A long-running local civic blog covering the area appears
  inactive (expired SSL cert, no content found past ~2015).
- Ran a Nextdoor poll + Patch post (without naming the specific township,
  to test the concept generically) asking whether neighbors would read a
  2-minute plain-English meeting recap — **result came back positive**,
  which is why this moved from prototype to "let's keep building."

## Distribution notes

- **Nextdoor**: no open bot-posting API for arbitrary apps — the Publish
  API requires partner approval and posting as an actual Nextdoor user.
  The no-approval Share Plugin (reader-clicks-to-share) works today.
- **Facebook Groups**: third-party automated posting was cut off by Meta in
  Feb 2024 — manual posting only.
- **Patch**: openly invites residents to post via its own "Post" button —
  manual, no public API found for automating it.
- **Email** is the only channel with a subscriber list you actually
  control. Buttondown's embed-subscribe form and RSS-to-email feature both
  work for this; RSS-to-email is a paid add-on (+$9/mo) beyond the free
  100-subscriber tier, worth it once there's an audience big enough that
  manually sending each digest becomes a real chore.

## Open next steps

1. Merge `generate_digest.py`'s output template with the styled `index.html`
   so a script run updates the real page directly, not a separate generic
   file.
2. Automate discovery of new Tredyffrin meetings. The meeting-index page
   (tredyffrin.org/Boards-Commissions/Board-of-Supervisors/Board-of-Supervisors-Meetings)
   lists every meeting with a predictable per-meeting page URL
   (`/Minutes-and-agenda/{year}-Board-of-Supervisors/{MMDDYYYY}-BOS-Meeting`),
   so a script could check it periodically and only pass in meetings whose
   date isn't already in `digest_data.json` — the current version still
   requires the URL to be found and passed in by hand.
3. Cross-meeting "storyline" detection (e.g. the Chase Road Park thread
   tracked across three meetings in the initial prototype) is currently done
   by a human reading multiple meetings side by side — worth treating as its
   own problem rather than folding into single-meeting summarization.
4. Decide on public hosting again now that the interest poll came back
   positive — options discussed: GitHub Pages (free, but requires a public
   repo on the free tier), Cloudflare Pages + Access (free, can be gated to
   just you or a small list), or staying local/private longer while more
   townships get added.
5. Expand beyond Tredyffrin — every Chester County municipality has its own
   site and PDF format, so this is real per-township work, not a config
   change.
