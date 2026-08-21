# Tredyffrin Meeting Digest

Plain-language digests of Tredyffrin Township Board of Supervisors meetings,
generated from the township's official public meeting minutes — so residents
don't have to read a dense PDF or watch a multi-hour video to know what got
decided.

**Status:** working prototype, 3 real meetings summarized (May–July 2026),
validated with a positive Nextdoor/Patch interest poll. Not currently hosted
publicly — running locally for now.

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
cp .env.example .env            # then fill in your real Anthropic API key
```

The script reads `ANTHROPIC_API_KEY` from the environment. Either export it
in your shell, or use a tool like `python-dotenv` to load `.env`
automatically (not wired in yet — currently you'd `export
ANTHROPIC_API_KEY=sk-...` before running the script, or source `.env`
manually).

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
2. Automate discovery of new Tredyffrin meetings (currently: manually check
   tredyffrin.org and pass the PDF URL in).
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
