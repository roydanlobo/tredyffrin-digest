# Chester County Meeting Digest

Plain-language digests of township Board of Supervisors meetings, generated
from each township's official public meeting minutes — so residents don't
have to read a dense PDF or watch a multi-hour video to know what got
decided.

**Status:** live at https://digest.platformlens.net/. Tredyffrin Township: 7
real meetings summarized (February–July 2026), validated with a positive
Nextdoor/Patch interest poll. Limerick Township was onboarded and had 2
real meetings summarized, then paused — see "Limerick: paused, not deleted"
below.

## What's here

- `index.html` — the Tredyffrin digest page.
- `activities.html` / `activities.json` — the separate kids' activities page
  and its data (edit the JSON to add listings).
- `feed-tredyffrin.xml` — the RSS 2.0 feed for the Tredyffrin digest.
- `digest_data_tredyffrin.json` — the
  underlying data (date, tags, highlights, source URL). This
  is the source of truth; the RSS feeds (and a generic fallback HTML page,
  see below) are rendered from it.
- `generate_digest.py` — the pipeline: given a minutes PDF (URL or local
  file), a meeting date, and `--township`, it extracts the text, asks
  Claude to write a plain-language digest (tags + highlight bullets),
  appends it to that township's data file, and re-renders that township's
  RSS feed and a generic HTML view.

  Note: the script renders to `<township>-digest-generated.html`, a plain
  fallback template — it does **not** update the real hand-styled pages
  (`index.html`) directly. Merging that is on the
  to-do list below; for now, updating the real pages after a new meeting is
  a manual step (or ask the assistant to do it, same as for the initial
  backfill).
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
far as the site can tell. If a township's site changes
its protection or blocks even Playwright, `--file` (pointing at a
manually-downloaded copy) is the fallback either way.

## Usage — after a new meeting posts minutes

1. Check the township's site for the new minutes PDF once it's posted
   (usually a few weeks after the meeting itself — minutes are typically
   approved at the following meeting before being published).
2. Run the script with `--township`:

   ```bash
   python generate_digest.py --township tredyffrin --url "<minutes-pdf-url>" --date "2026-09-08"
   ```

   `--township` defaults to `tredyffrin` if omitted, so old commands from
   before multi-township support still work unchanged.

3. **Read the output against the source PDF before publishing anything.**
   These digests state facts about local government — dollar amounts, vote
   counts, who said what — and an AI summary of a scanned PDF can misread a
   number. A quick check is cheap insurance.
4. Update the real page (`index.html`) with the new
   entry — this isn't automated yet (see "What's here" above).

To just rebuild a township's RSS/generic HTML from existing data without
adding a new meeting: `python generate_digest.py --township tredyffrin --render-only`.

### Note on the February–April 2026 Tredyffrin entries

Those four meetings were backfilled directly (not run through this script
locally) — the assistant found the minutes URLs and extracted/summarized
their content via its own web-fetch tooling, then added the entries by
hand, in the same format the script produces. That's a reasonable one-time
way to seed history, but it means those four entries haven't been through
the exact same pipeline as the May–July ones. Worth a spot-check against
the source PDFs (linked on each entry) before treating them as fully
verified, same as any other digest.

### Limerick: paused, not deleted

Limerick Township was researched, onboarded, and had two real meetings
(July 28 and August 4, 2026) summarized and published — then paused, since
its PDFs turned out to be significantly more work to maintain than the
other two townships: instead of one meeting per PDF, its newer postings
bundle several meetings' minutes, the current agenda, and ~85 pages of
unrelated exhibits into a single 100+ page "Resident Packet" (one real
example ran 33MB). A real parser (`extract_minutes_section()`, still in
`generate_digest.py`) was built and tested to isolate just the right
Minutes section from a packet, and it works, but every future Limerick
meeting would need that same kind of care, more upkeep than seemed worth
it for a third township at this stage.

Nothing was thrown away: `limerick.html`, `digest_data_limerick.json`, and
`feed-limerick.xml` still exist on disk with the two real entries, just no
longer linked from the live site or referenced in `TOWNSHIPS`. To revive
it: un-comment the `"limerick"` block in `TOWNSHIPS` (see the comment right
above it in `generate_digest.py`), re-add its dropdown option and footer
link to `index.html`, and re-add its cross-links there.
If you do, the site's `CNAME`/GitHub Pages setup doesn't need anything
new — `limerick.html` still deploys automatically as part of the repo,
just wasn't being linked to.

## Buttondown: one newsletter, tags (segmentation not yet purchased)

The digest and the kids' activities page share one Buttondown newsletter
(`SummarizeMyDigest`). Each page's subscribe form silently tags the
subscriber: `tredyffrin` (digest page) or `activities` (activities page);
see the hidden `tag` field in each form. **Tagging & segmentation is a paid
Buttondown add-on ($9/mo)** and isn't on the free plan, so right now the
tag only labels subscribers (the tags show up in a subscriber export). It
doesn't filter anything.

Rule until the add-on is bought: never send an activities email to the whole
list, because most subscribers signed up for township digests only. If the
activities list is tiny, email those few people yourself (BCC). Once
segmentation is purchased:

1. In Buttondown, go to Tags and make sure `tredyffrin` and `activities`
   exist.
2. Get each tag's ID (`GET /v1/tags` with your API key, or the dashboard).
3. Set the digest tag as an environment variable:
   ```bash
   export BUTTONDOWN_TAG_TREDYFFRIN=sub_tag_...
   ```
4. `generate_digest.py` and `catchup_email.py` will then filter the digest
   draft to just that tag's subscribers. If the ID isn't set, drafts go out
   untargeted (to everyone on the newsletter) and the script prints a
   warning so you notice before sending. Untagged older subscribers would
   need tagging `tredyffrin` first.

### Catching up new subscribers

`catchup_email.py --township tredyffrin` rolls up every
entry in that township's data file into a single DRAFT email — useful for
a subscriber who joins today and would otherwise miss all the history.
Like every other draft here, it's created as a draft only; nothing sends
until you review it in the Buttondown dashboard and hit Send.

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
   script run updates `index.html` directly, not a
   separate generic file.
2. Automate discovery of new meetings per township (each township needs
   its own logic — see the module docstring in `generate_digest.py` for
   each site's known URL pattern). Currently the URL still has to be found
   and passed in by hand for both.
3. Cross-meeting "storyline" detection (e.g. the Chase Road Park thread
   tracked across three Tredyffrin meetings) is currently done by a human
   reading multiple meetings side by side — worth treating as its own
   problem rather than folding into single-meeting summarization.
4. Create the two Buttondown tags and set the `BUTTONDOWN_TAG_*` env vars
   (see above) — without them, drafts go out untargeted.
5. Revisit Limerick once there's bandwidth for its extra upkeep (see
   "Limerick: paused, not deleted" above) — its two real meetings are
   already summarized and waiting.
6. Beyond these: every Chester/Montgomery County municipality has its own
   site and PDF format, so each additional township is real per-site work,
   not a config change.
