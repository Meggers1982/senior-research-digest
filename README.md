# Senior Living Research Digest

Automated pipeline that searches PubMed for recent senior-care research, uses
Claude to write a plain-language digest for older adults and their caregivers,
fact-checks its own output against the source abstracts, and publishes every
run to a browsable dashboard.

## How it works

`.github/workflows/daily-digest.yml` runs `scripts/main.py` on a daily cron
(09:00 UTC) via GitHub Actions. Each run:

1. **Searches PubMed** (`pubmed.py`) across ~167 curated aging/gerontology
   journals (`journals.py`) for articles from the last 90 days, optionally
   filtered to a subject focus. ISSNs are searched in batches of 25 and the
   per-batch results are merged by fractional rank, so each batch is
   represented in proportion to what it found rather than the earliest
   batches filling the 200-PMID cap on their own.
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
   real outlets that specific angle could go to, for pitching ideation. It
   then goes back through the new digest's studies one at a time and adds a
   "Story Ideas by Study" section covering every study with its own
   pitchable angle, so nothing worth pitching gets missed.
6. **Rebuilds the dashboard** (`build_dashboard_data.py`) — parses every
   digest + fact-check in `outputs/` into `docs/data/index.json` plus one
   file per run under `docs/data/runs/`.
7. **Commits everything back** — `outputs/`, `topic_memory/`, and `docs/` are
   committed and pushed by the workflow so history accumulates in the repo.

Nothing is ever overwritten: if two digests would land on the same filename
(e.g. two broad runs in the same month), `main.py` appends "(Part N)".

A healthy run finishes in about six minutes. The workflow caps itself with
`timeout-minutes` (30 for the job, 20 for the pipeline step, 10 for the Vercel
deploy) so a hung run fails fast instead of sitting on GitHub's six-hour
default.

## Dashboard

`docs/index.html` is a static, no-build dashboard that reads
`docs/data/index.json` and lets you browse **every digest ever generated**,
not just the latest — filter by topic, search by headline/PMID/journal, and
see each study's fact-check verdict inline. When a run includes a feature
pitch and/or per-study pitch ideas, matching "Jump to Feature Pitch" and
"Jump to Story Ideas" links appear in the run header and scroll straight to
the **Bigger Picture: Feature Pitch** and **Story Ideas by Study** blocks at
the bottom of the page. Prose blocks render `**bold**` and `*italic*` from the source markdown
(both on screen and in the .docx export), and the citation table gets its own
horizontal scroll area so wide tables don't push the whole page sideways on
phones.

The run list is keyboard-operable (tab to a run, Enter or Space to open it)
and the sticky offsets read the header's measured height from a `--header-h`
CSS variable rather than a hardcoded guess, so nothing tucks underneath it
when the header grows at narrow widths. On phones the list is capped at 45vh
with its own scroll, so the digest itself stays near the top of the page
instead of sitting below every run card.

Data is split so first load stays flat as runs accumulate: `index.json` carries
only what the sidebar and search need (~118 KB, including a prebuilt search
blob per run), and a run's full body is fetched from `data/runs/<id>.json` when
you open it, then cached for the session. The .docx library is vendored under
`docs/vendor/` and loaded on the first export rather than on page load, so no
CDN sits in the critical path.

It's deployed to Vercel from this repo (private repo — GitHub Pages isn't
available on the free plan for private repos, which is why Vercel is used
instead of Pages). Vercel's Git integration is deliberately **disconnected**,
so pushing to `main` does *not* redeploy. The only thing that publishes is an
explicit `vercel deploy --prod` run from inside `docs/` (where the `.vercel`
link file lives) — either by hand, or from the "Deploy dashboard to Vercel"
step of `daily-digest.yml`. In practice the daily workflow run is what keeps
the live dashboard current with `outputs/`; a manual code change to the
dashboard needs a manual deploy to show up before then.

Don't reconnect Git integration without first moving the `.vercel` link to the
repo root and setting Root Directory to `docs`. With it connected at the repo
root, every push spawns a competing build that finds no `index.html`, succeeds
empty, and steals the production alias — which reads as a 404 on the live site.

To view it locally without deploying anything:

```bash
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```

To rebuild the dashboard data by hand (e.g. after editing a past
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
`DIGEST_FOCUS="falls" python3 main.py`). An empty value is treated as "no
override" and falls through to the rotation, so the broad digest cannot be
forced this way — it only runs when the rotation lands on it.

### Choosing topic wording

A focus is ANDed into the PubMed query as an exact phrase match
(`"<focus>"[Title/Abstract]`) with no synonym or MeSH expansion, so the exact
string decides how many articles a topic can draw from. Measured over one
90-day window across the 146 journals in the list as of 2026-08-21:

| Wording | Articles |
| --- | --- |
| `falls` | 267 |
| `fall prevention` | 76 |
| `cognitive decline` | 531 |
| `mild cognitive impairment` | 338 |
| `vision loss` | 33 |

`falls` replaced `fall prevention` in the rotation on 2026-08-21 for this
reason. Note that closely related phrasings pull largely separate literature —
a topic is only as broad as its literal string. Aim for roughly 75+ articles;
the pipeline reads up to 40 abstracts and selects ~22 studies, so a thinner
pool produces a thin digest.

Renaming a rotation topic breaks two continuity links, both keyed to the focus
string: `topic_memory/<slug>.md` (rename the file to match) and the prior-digest
lookup in `trends.py`, which matches the `Focus` field exactly and so will not
see digests filed under the old name.

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
- `SERPAPI_API_KEY` — optional, shared with `agingwire-research-intelligence`
  and `trending-content`. Without it the weekly topic-demand report produces
  nothing and the coverage check is skipped, so pitch suggestions keep the full
  candidate list. Roughly 8 Google News searches per daily run plus a weekly
  Trends batch.

### Journal list

`journals.py` holds `(journal name, ISSN)` pairs — electronic ISSN where one
exists. A wrong ISSN fails silently: PubMed returns it in `phrasesnotfound`
and the journal contributes nothing, so check a new entry against
`https://www.ncbi.nlm.nih.gov/nlmcatalog/journals` and confirm it returns a
non-zero count for `<issn>[issn]` before adding it.

Audited against the NLM Catalog on 2026-09-03: of the 75 currently
MEDLINE-indexed journals under NLM's "Geriatrics" broad subject term, the only
English-language gaps were palliative/hospice nursing titles and the
*Alzheimer's & Dementia* companion journals. That audit added 21 journals
(146 → 167) and corrected the Health Affairs ISSN, which PubMed had never
recognized. Journals with no PubMed content in the last 12 months — *Journal of
Global Ageing*, *Translational Medicine of Aging*, *Generations* — are kept in
the list in case they resume publishing.

## Repo layout

```
scripts/
  main.py                  entry point — orchestrates the full pipeline
  pubmed.py                PubMed E-utilities client
  journals.py              curated list of (journal name, ISSN) pairs searched
  digest_generator.py      Claude prompt + call that writes the digest
  fact_checker.py          Claude prompt + call that fact-checks the digest
  trends.py                Claude prompt + call for trends/feature-pitch + topic memory
  outlets.py               pitch targets from the publisher registry, clinical-topic matching
  web_coverage.py          Google News check — has the press already run these studies?
  topic_demand.py          weekly Google Trends report on the focus rotation
  build_dashboard_data.py  parses outputs/*.md into docs/data/index.json + runs/
outputs/                   every digest + fact-check ever generated (.md)
topic_memory/              per-topic running memory used by trends.py
docs/                      static dashboard (index.html + data/), deployed to Vercel
config/digest_config.json  audience and rotation settings
config/media/              publisher registries, exported from the AgingWire workbooks
tests/                     outlet matching and coverage-gate tests
.github/workflows/         daily cron (daily-digest.yml), weekly topic demand (topic-demand.yml)
.gitignore                 keeps the local Vercel CLI link dir (.vercel) untracked
```

## Pitch targets from the publisher database

`config/media/*.csv` is an export of the AgingWire B2B and B2C publisher
prospecting workbooks. **The workbooks are the source of truth** —
`agingwire-research-intelligence` holds a second export of the same files, so
re-export to both when a workbook changes rather than editing either CSV. The
repos stay independent; they share reference data, not a runtime dependency.

`scripts/outlets.py` picks pitch targets for the run's focus and injects them
into the feature-pitch prompt, replacing a hardcoded list of nine example
outlets. Each candidate carries its tier and the workbook's own
`Why It Matters / Pitch Angle` note. The prompt still allows the model to name a
publication the registry does not have.

Matching differs from AgingWire's deliberately. Its topics are the vocabulary
outlets use ("housing", "workforce", "medicare"), so terms match directly. This
digest's focus rotation is clinical, and no consumer publication lists
"sarcopenia" in its coverage. Clinical topics are therefore mapped to the
consumer subject they belong to, relevance *bands* rather than ranks — ranking on
raw hit count put Watchlist fitness titles above Next Avenue for osteoporosis,
and ranking on data fit alone dropped the dementia specialists — and ordering
inside a band is by how well an outlet takes a data story.

## Has the press already run it?

`scripts/web_coverage.py` asks Google News whether the leading studies have
already been written up, and every outlet it finds is excluded from the pitch
suggestions. Pitching a story to the publication that just ran it is the one
suggestion guaranteed to be wrong.

Google ranks by topical relevance, so results are filtered on headline overlap
with the study title — without that gate a grip-strength study matches articles
about grip strengtheners for climbers. Requires `SERPAPI_API_KEY`; without it
the check is skipped, the run says so, and the pitch simply keeps the full
candidate list.

## Topic demand (optional)

`scripts/topic_demand.py` ranks the `focus_rotation` topics by Google Trends
search interest and lists rising related queries around "senior health" and
"elderly health", writing `outputs/topic-demand.md`. It runs weekly, and
**never edits `config/digest_config.json`** — topic wording drives PubMed yield
here, so the rotation stays a manual, reviewed edit and this only informs it.

Requires `SERPAPI_API_KEY`; without it the script exits cleanly and the workflow
commits nothing. Trends values are Google's relative 0-100 index, not search
counts, so a large percentage rise from a low base is still a low base — terms
under a noise floor are dropped rather than reported as spikes, as are
`partial_data` points, which cover an incomplete period and read as a crash.

