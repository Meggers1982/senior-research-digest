# Senior Living Research Digest

Automated pipeline that searches PubMed for recent senior-care research, uses
Claude to write a plain-language digest for older adults and their caregivers,
fact-checks its own output against the source abstracts, and publishes every
run to a browsable dashboard.

## How it works

`.github/workflows/daily-digest.yml` runs `scripts/main.py` on a daily cron
(09:00 UTC) via GitHub Actions. Each run:

1. **Searches PubMed** (`pubmed.py`) across ~146 curated aging/gerontology
   journals (`journals.py`) for articles from the last 90 days, optionally
   filtered to a subject focus.
2. **Picks today's focus** — either a manual override, a fixed topic from
   `config/digest_config.json`, or the next topic in the daily rotation
   (`main.py`'s `DEFAULT_FOCUS_ROTATION` / `config["focus_rotation"]`).
3. **Generates the digest** (`digest_generator.py`) — Claude selects the most
   newsworthy studies from up to 40 abstracts and writes a structured entry
   for each (headline, study summary, why it matters, story angles for two
   audiences, caveats).
4. **Fact-checks itself** (`fact_checker.py`) — a second Claude pass compares
   every entry against the original abstract and flags inaccuracies with a
   ✅/⚠️/❌ verdict per study.
5. **Compares against history** (`trends.py`) — Claude compares the new
   digest to the most recent prior digest on the same topic and to a running
   per-topic memory file (`topic_memory/<topic>.md`), producing a "Research
   Trends & Continuity" section plus a "Bigger Picture: Feature Pitch" if the
   batch suggests a larger story. When there is a pitch, it also suggests 3-4
   real outlets that specific angle could go to, for pitching ideation.
6. **Rebuilds the dashboard** (`build_dashboard_data.py`) — parses every
   digest + fact-check in `outputs/` into `docs/data/digests.json`.
7. **Commits everything back** — `outputs/`, `topic_memory/`, and `docs/` are
   committed and pushed by the workflow so history accumulates in the repo.

Nothing is ever overwritten: if two digests would land on the same filename
(e.g. two broad runs in the same month), `main.py` appends "(Part N)".

## Dashboard

`docs/index.html` is a static, no-build dashboard that reads
`docs/data/digests.json` and lets you browse **every digest ever generated**,
not just the latest — filter by topic, search by headline/PMID/journal, and
see each study's fact-check verdict inline.

It's deployed to Vercel from this repo (private repo — GitHub Pages isn't
available on the free plan for private repos, which is why Vercel is used
instead of Pages). Every push to `main` (including the bot's daily commit)
triggers a redeploy, so the live dashboard always reflects the latest
`outputs/`.

To view it locally without deploying anything:

```bash
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```

To rebuild `docs/data/digests.json` by hand (e.g. after editing a past
digest):

```bash
python3 scripts/build_dashboard_data.py
```

This parser expects the exact markdown structure Claude is instructed to
produce in `digest_generator.py`'s `SYSTEM_PROMPT` (`### N. Headline`,
`**Journal:**`, `**PMID:**`, `**Story angles:**` with `To`/`About` bullets,
etc.) and `fact_checker.py`'s per-study verdict line
(`**PMID:** ... | **Verdict:** ...`). If either prompt's output format
changes, update the corresponding regexes in `build_dashboard_data.py` too.

A few historical runs in `outputs/` were truncated mid-generation (hit
`max_tokens` before the retry logic caught it) — the parser handles this by
leaving the missing fields as `—` rather than failing, and the dashboard
renders them the same way.

## Running locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export NCBI_API_KEY=...        # optional — raises PubMed rate limit from 3 to 10 req/sec
cd scripts
python3 main.py
```

Set `DIGEST_FOCUS` to override today's rotation (e.g.
`DIGEST_FOCUS="fall prevention" python3 main.py`).

## Configuration

Edit `config/digest_config.json` and commit — the next run picks it up:

- `subject_focus` — leave empty to rotate through `focus_rotation` daily, or
  set a fixed topic to always search that one.
- `focus_rotation` — the list of topics rotated through by day-of-year.
- `primary_audience` / `secondary_audience` — who the two story-angle bullets
  per study are written for.
- `days_back` — PubMed lookback window (days).

## Required secrets (GitHub Actions)

Set these under repo Settings → Secrets and variables → Actions:

- `ANTHROPIC_API_KEY` — required, used for digest generation, fact-checking,
  and trends synthesis.
- `NCBI_API_KEY` — optional, raises the PubMed rate limit.

## Repo layout

```
scripts/
  main.py                  entry point — orchestrates the full pipeline
  pubmed.py                PubMed E-utilities client
  journals.py              curated list of (journal name, ISSN) pairs searched
  digest_generator.py      Claude prompt + call that writes the digest
  fact_checker.py          Claude prompt + call that fact-checks the digest
  trends.py                Claude prompt + call for trends/feature-pitch + topic memory
  build_dashboard_data.py  parses outputs/*.md into docs/data/digests.json
outputs/                   every digest + fact-check ever generated (.md)
topic_memory/              per-topic running memory used by trends.py
docs/                      static dashboard (index.html + data/digests.json), deployed to Vercel
config/digest_config.json  audience and rotation settings
.github/workflows/         daily cron (daily-digest.yml)
```
