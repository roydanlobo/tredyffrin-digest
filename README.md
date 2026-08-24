# Chester County Meeting Digest

Plain-language digests of township Board of Supervisors meetings, generated
from each township's official public meeting minutes — so residents don't
have to read a dense PDF or watch a multi-hour video to know what got
decided.

**Status:** live at https://digest.platformlens.net/. Tredyffrin Township: 7
real meetings summarized (February–July 2026), validated with a positive
Nextdoor/Patch interest poll. Upper Merion Township: 4 real meetings
summarized (June–August 2026). Limerick Township: just onboarded (site
page, RSS feed, pipeline support in place), no meetings processed yet —
see "Why Limerick doesn't have content yet" below.

## What's here

- `index.html` — the Tredyffrin digest page.
- `upper-merion.html` — the Upper Merion digest page.
- `limerick.html` — the Limerick digest page. All three pages have a
  "Viewing digests for" dropdown at the top to switch between them.
- `feed-tredyffrin.xml` / `feed-upper-merion.xml` / `feed-limerick.xml` —
  one RSS 2.0 feed per township, so subscribing to one never pulls in
  another's items.
- `digest_data_tredyffrin.json` / `digest_data_upper-merion.json` /
  `digest_data_limerick.json` — the underlying data (date, tags,
  highlights, source URL) per township. This is the source of truth; the
  RSS feeds (and a generic fallback HTML page, see below) are rendered
  from it.
- `generate_digest.py` — the pipeline: given a minutes PDF (URL or local
  file), a meeting date, and `--township`, it extracts the text, asks
  Claude to write a plain-language digest (tags + highlight bullets),
  appends it to that township's data file, and re-renders that township's
  RSS feed and a generic HTML view.

  Note: the script renders to `<township>-digest-generated.html`, a plain
  fallback template — it does **not** update the real hand-styled pages
  (`index.html`, `upper-merion.html`, `limerick.html`) directly. Merging
  those is on the to-do list below; for now, updating the real pages after
  a new meeting is a manual step (or ask the assistant to do it, same as
  for the initial backfill).
- `catchup_email.py` — one-time "here's everything you missed" email
  generator, per township (see below).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # one-time browser download, see note below
cp .env.example .env            # then fill in your real Anthropic API key
```

The script reads `ANTHROPIC_API_KEY`, and optionally `BUTTONDOWN_API_KEY`
plus the per-township `BUTTONDOWN_TAG_*` variables, from the environment.
Either export them in your shell, or use a tool like `python-dotenv` to
load `.env` automatically (not wired in yet — currently you'd export them
manually before running the script). Environment variables set with
`$env:VAR = "..."` in PowerShell only last for that terminal session — use
the System Environment Variables GUI if you want them to persist.

### Why Playwright?

Tredyffrin's site blocks plain HTTP downloads (Python's `requests`, even
with full browser-matching headers) but allows real browsers through — this
looks like TLS/behavioral fingerprinting rather than a simple header check,
since a confirmed-real URL that loads fine by hand still 403'd from
`requests`. `download_pdf()` drives a real headless Chromium browser via
Playwright instead, which gets past it because it *is* a real browser as
far as the site can tell. This isn't Tredyffrin-specific code — it's since
been confirmed working for Upper Merion too. Limerick's AgendaCenter file
endpoints show the same shape of blocking in testing (listing pages fetch
fine, the PDF links themselves don't via plain tooling), so Playwright
should work there as well, but that's not proven yet — worth confirming on
the first real Limerick run. If a township's site changes its protection or
blocks even Playwright, `--file` (pointing at a manually-downloaded copy)
is the fallback either way.

## Usage — after a new meeting posts minutes

1. Check the township's site for the new minutes PDF once it's posted
   (usually a few weeks after the meeting itself — minutes are typically
   approved at the following meeting before being published).
2. Run the script with `--township`:

   ```bash
   python generate_digest.py --township tredyffrin --url "<minutes-pdf-url>" --date "2026-09-08"
   python generate_digest.py --township upper-merion --url "<minutes-pdf-url>" --date "2026-05-14"
   python generate_digest.py --township limerick --url "<minutes-pdf-url>" --date "2026-01-20"
   ```

   `--township` defaults to `tredyffrin` if omitted, so old commands from
   before multi-township support still work unchanged.

3. **Read the output against the source PDF before publishing anything.**
   These digests state facts about local government — dollar amounts, vote
   counts, who said what — and an AI summary of a scanned PDF can misread a
   number. A quick check is cheap insurance. This matters even more for
   Limerick, given how contentious the data center topic already is locally
   — a wrong number or an overstated "the board voted X" there does more
   damage than the same mistake somewhere quieter.
4. Update the real page (`index.html`, `upper-merion.html`, or
   `limerick.html`) with the new entry — this isn't automated yet (see
   "What's here" above).

To just rebuild a township's RSS/generic HTML from existing data without
adding a new meeting: `python generate_digest.py --township upper-merion --render-only`.

### Note on the February–April 2026 Tredyffrin entries

Those four meetings were backfilled directly (not run through this script
locally) — the assistant found the minutes URLs and extracted/summarized
their content via its own web-fetch tooling, then added the entries by
hand, in the same format the script produces. That's a reasonable one-time
way to seed history, but it means those four entries haven't been through
the exact same pipeline as the May–July ones. Worth a spot-check against
the source PDFs (linked on each entry) before treating them as fully
verified, same as any other digest.

### Upper Merion is now real content, and a quirk worth knowing

Upper Merion's site (umtownship.org) disallows all automated fetching in
its robots.txt, so unlike Tredyffrin, the assistant can't read or summarize
its minutes itself — every Upper Merion entry had to be run through the
local Playwright pipeline. Four real meetings (June–August 2026) are now
in `digest_data_upper-merion.json` and on `upper-merion.html` this way.

One quirk found while building those: Upper Merion's AgendaCenter sometimes
uploads the actual **minutes** content under the **Agenda** URL category
(`/AgendaCenter/ViewFile/Agenda/...`) instead of a separate Minutes
category — a CivicPlus-platform quirk, not a bug in this project. The
script doesn't care about URL folder naming, it just downloads whatever URL
you give it, but *you* need to check each PDF's actual content (does it
show votes/outcomes, or just a proposed agenda?) before treating a given
URL as authoritative, regardless of which folder it's filed under.

### Why Limerick doesn't have content yet — and its "Resident Packet" format

Limerick was researched and onboarded (config, site page, RSS feed) but no
meetings have been run through the pipeline yet. Limerick runs on the same
CivicPlus AgendaCenter platform as Upper Merion.

Two older standalone Minutes PDFs are known to exist (single meeting per
file, same shape as Tredyffrin/Upper Merion — no splitting needed):

- February 17, 2026 — `https://www.limerickpa.org/AgendaCenter/ViewFile/Minutes/_02172026-617`
- January 20, 2026 — `https://www.limerickpa.org/AgendaCenter/ViewFile/Minutes/_01202026-614`

But Limerick appears to have since moved to a **consolidated "Resident
Packet" format**: checked for a standalone Minutes entry matching the
August 19, 2026 packet (`_08192026-642`) and it doesn't exist under the
Minutes category at all — that packet only exists under Agenda. Confirmed
by reading a real one (the user shared `8-19-26 Resident Packet.pdf`
directly, 109 pages): it bundles that meeting's own Agenda (pages 1-3), the
Minutes of the two meetings *before* it pending approval (July 28 on pages
13-19, August 4 on pages 20-24), then ~85 pages of unrelated land-
development resolutions, survey exhibits, and a police presentation on
e-bike safety — not minutes at all.

Each Minutes section is reliably self-labeled though: its first page reads
"LIMERICK TOWNSHIP - BOARD OF SUPERVISORS &lt;DATE&gt;" / "REGULAR MEETING
MINUTES", and every following page in that section carries a running header
"Board of Supervisors / &lt;date&gt; / Page N, Minutes". `generate_digest.py`
now has `extract_minutes_section()`, which uses those two header patterns
to pull out just the pages for a given `--date` — tested directly against
the real August 19 packet (correctly isolated both the July 28 and August 4
sections, 15,135 and 8,380 characters respectively, and correctly returned
nothing for a date that isn't in the packet). Limerick's `TOWNSHIPS` entry
now has `"bundled_packet": True`, so `main()` automatically routes through
this instead of the plain `extract_text()` whenever `--township limerick`
is used — no extra flag needed, just pass the packet PDF (via `--url` or
`--file`) and the correct `--date`.

What's still unproven: whether `download_pdf()`'s Playwright approach
actually fetches these Resident Packet PDFs from limerickpa.org — the one
tested against was manually downloaded and shared directly, not pulled by
the pipeline itself. Worth confirming on the first real run. If a future
packet ever puts a Minutes section past page 60,
`extract_minutes_section()`'s `max_scan_pages` will need raising (see its
docstring).

Limerick has had real local news coverage of resident pushback on a
proposed data center, plus its long-running proximity to the Limerick
Generating Station (nuclear) — worth being extra careful with accuracy here
specifically (see the note in "Usage" above).

The likely official video channel is
`https://www.youtube.com/@LimerickTownship1726`, found via search but not
independently confirmed — check it actually is the meeting-recording
channel before it's relied on for a "Video archive" link the way Tredyffrin
and Upper Merion's pages use one.

## Buttondown: one newsletter, three tags (currently unused — free plan)

All three townships share one Buttondown newsletter (`SummarizeMyDigest`)
rather than running separate accounts. Each page's subscribe form still
silently tags the subscriber (`tredyffrin`, `upper-merion`, or `limerick`
— see the hidden `tag` field in each page's form), but **tagging &
segmentation is a paid Buttondown add-on ($9/mo)**, not included on the
free plan. As of now, none of the `BUTTONDOWN_TAG_*` env vars below are
set, so every draft goes out to every subscriber regardless of which page
they signed up from — the per-township tag on signup is stored (harmless,
and useful later if this gets upgraded) but doesn't currently filter
anything. This is a deliberate choice at 9 subscribers, not a bug — each
page's subscribe-form fine print says as much, and points to that
township's RSS feed for anyone who wants just one township without the
email noise.

If/when it's worth paying for (bigger list, people complaining about
getting all three townships), here's how to make targeted sending actually
work:

1. In Buttondown, go to Tags and create three tags: `tredyffrin`,
   `upper-merion`, and `limerick`.
2. Get each tag's ID (`GET /v1/tags` with your API key, or the dashboard).
3. Set them as environment variables:
   ```bash
   export BUTTONDOWN_TAG_TREDYFFRIN=sub_tag_...
   export BUTTONDOWN_TAG_UPPER_MERION=sub_tag_...
   export BUTTONDOWN_TAG_LIMERICK=sub_tag_...
   ```
4. `generate_digest.py` and `catchup_email.py` will then filter each
   township's draft to just that tag's subscribers automatically. If a
   tag ID isn't set, drafts for that township go out untargeted (to
   everyone on the newsletter) and the script prints a warning so you
   notice before sending.

### Catching up new subscribers

`catchup_email.py --township tredyffrin` (or `upper-merion` / `limerick`)
rolls up every entry in that township's data file into a single DRAFT
email — useful for a subscriber who joins today and would otherwise miss
all the history. Like every other draft here, it's created as a draft
only; nothing sends until you review it in the Buttondown dashboard and
hit Send. (Limerick's data file is currently empty, so this has nothing to
roll up until the first real meeting is processed.)

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
  which is why this moved from prototype to "let's keep building," and
  later to adding a second township.

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

1. Merge `generate_digest.py`'s output template with the styled pages so a
   script run updates `index.html`/`upper-merion.html`/`limerick.html`
   directly, not a separate generic file.
2. Process real Limerick meetings — the two URLs above are a starting
   point; run them through `--township limerick` locally, and confirm the
   Playwright download step actually works against limerickpa.org (see
   "Why Limerick doesn't have content yet" above — likely, not yet proven).
3. Automate discovery of new meetings per township (each township needs
   its own logic — see the module docstring in `generate_digest.py` for
   each site's known URL pattern). Currently the URL still has to be found
   and passed in by hand for all three.
4. Cross-meeting "storyline" detection (e.g. the Chase Road Park thread
   tracked across three Tredyffrin meetings) is currently done by a human
   reading multiple meetings side by side — worth treating as its own
   problem rather than folding into single-meeting summarization.
5. Create the three Buttondown tags and set the `BUTTONDOWN_TAG_*` env vars
   (see above) — without them, drafts go out untargeted.
6. Confirm the likely Limerick YouTube channel is actually the official
   meeting-recording one before adding a "Video archive" link to real
   Limerick entries the way the other two townships have.
7. Beyond these three: every Chester/Montgomery County municipality has its
   own site and PDF format, so each additional township is real per-site
   work, not a config change.
