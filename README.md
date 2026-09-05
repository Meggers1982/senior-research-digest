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
   newsworthy studies from up to 40 abstracts and returns one **record** per
   study (headline, study summary, why it matters, story angles for two
   audiences, caveats). `digest_render.py` turns those into the markdown; see
   [The model returns records](#the-model-returns-records).
4. **Fact-checks itself** (`fact_checker.py`) — a second Claude pass compares
   every entry against the original abstract and returns a verdict record per
   study, rendered by `factcheck_render.py` with a ✅/⚠️/❌ badge.
5. **Checks whether the press already has it** (`web_coverage.py`) — a Google
   News lookup per study, cached by PMID. Outlets already on a story are
   excluded from the pitch suggestions, and the result becomes the study's
   coverage state on the dashboard.
6. **Compares against history** (`trends.py`) — Claude compares the new
   digest to the most recent prior digest on the same topic and to a running
   per-topic memory file (`topic_memory/<topic>.md`), producing a "Research
   Trends & Continuity" section plus a "Bigger Picture: Feature Pitch" if the
   batch suggests a larger story. When there is a pitch, it also suggests 3-4
   real outlets that specific angle could go to, for pitching ideation. It
   then goes back through the new digest's studies one at a time and adds a
   "Story Ideas by Study" section covering every study with its own
   pitchable angle, so nothing worth pitching gets missed.
7. **Scores and rebuilds the dashboard** (`scoring.py`,
   `build_dashboard_data.py`) — parses every digest + fact-check in `outputs/`,
   scores each study, and writes `docs/data/index.json` plus one file per run
   under `docs/data/runs/`.
8. **Commits everything back** — `outputs/`, `topic_memory/`, `state/` and
   `docs/` are committed and pushed by the workflow so history accumulates in
   the repo. `state/` holds the coverage cache; the runner filesystem does not
   persist, so a cache that is not committed is a cache that is always empty.

Nothing is ever overwritten: if two digests would land on the same filename
(e.g. two broad runs in the same month), `main.py` appends "(Part N)".

`python -m pytest tests/ -q` runs before the pipeline in the same workflow. The
parsers that build the dashboard are regexes over model output and have drifted
silently before, so the suite is the thing that makes that loud. It touches no
API and costs nothing.

A healthy run finishes in about six minutes. The workflow caps itself with
`timeout-minutes` (30 for the job, 20 for the pipeline step, 10 for the Vercel
deploy) so a hung run fails fast instead of sitting on GitHub's six-hour
default.

## Dashboard

`docs/index.html` is a static, no-build dashboard that reads
`docs/data/index.json` and lets you browse **every digest ever generated**,
not just the latest.

**The pitch comes first.** The feature pitch and story ideas used to sit below
every study card — around 21 on an average run, which is where a reader gives up.
The order is pitch → story ideas → trends → studies → citations → limits.

**Studies are filterable.** Multi-select chips over score band, fact-check
verdict, study design, topic and editorial status, each carrying a live count of
what choosing it would leave. A group with only one value hides itself, which is
why Coverage does not appear on runs from before the coverage check ran.

**Editorial status per study** — to review, shortlisted, drafting, pitched,
published, passed, killed — held in `localStorage` and carried into the .csv
export. 1,122 archived studies with nowhere to record what you did about one is
the gap `freelance-opps-app` was built to close. `passed` and `killed` are both
negative and the difference is deliberate: `killed` is an editor saying no,
`passed` is you saying no, and only the second says anything about the score.

**"What this run does not tell you"** states the limits in words, measured off
the run rather than boilerplate. When coverage was never checked it says so, so
an absent "no coverage found" reads as "nobody looked" instead of "the story is
open".

Also: stat tiles for the run's headline numbers, `.docx` and `.csv` export, and
prose blocks that render `**bold**`, `*italic*` and `##` headings from the source
markdown while dropping `---` rules, which used to print as literal text. The
citation table gets its own horizontal scroll area so wide tables don't push the
page sideways on phones.

The design system is shared with `agingwire-research-intelligence` and
`freelance-opps-app` — see [Design system](#design-system).

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

### Design system

Ported from `freelance-opps-app` by way of `agingwire-research-intelligence`, so
the three read as one product rather than three tools that happen to share an
owner.

| | Value |
| --- | --- |
| Background / surface / border | `#f7f6f3` / `#ffffff` / `#e3e0d9` |
| Text / muted / faint | `#1c1b18` / `#6b675e` / `#918c81` |
| Accent / accent-soft | `#1f5f4f` / `#e6efeb` |
| Type | Source Sans 3 — 1.0625rem/600 card titles, 0.95rem/1.625 body |
| Measure | 56rem, centred |
| Radii / elevation | `0.5rem` / `0 1px 2px rgba(0,0,0,.03)` |

Three conventions worth keeping:

- **Chips are clickable, tags are not.** Facet chips are pills; tags and outlet
  chips are square-cornered. The shape is the affordance.
- **The caret and the SHOW/HIDE pill keep their size and resting opacity.** Both
  were raised on purpose after the collapse control shipped invisible.
- **Light is the default and the page does not follow the OS theme.** The
  `[data-theme]` rules sat in this file for months with no JS setting the
  attribute, so a dark-mode browser could never reach the light palette. Dark is
  opt-in through the toggle, remembered under `srd-theme`.

`tests/test_dashboard.py` pins the JS-to-JSON field contract and then executes
the script in Node over a real run, so a `ReferenceError` fails CI rather than
showing a blank page. It also pins the three conventions above.

### Publishing it

**Live at <https://docs-one-beryl.vercel.app>.** The Vercel project is called
`docs`, not `senior-research-digest` — it was auto-named after the directory it
was first linked from, so neither the repo name nor the project list makes the
connection obvious.

It's deployed to Vercel from this repo (private repo — GitHub Pages isn't
available on the free plan for private repos, which is why Vercel is used
instead of Pages). Vercel's Git integration is deliberately **disconnected**, so
**pushing to `main` does *not* redeploy.** Three ways to publish:

| | When to use it |
| --- | --- |
| Actions → **Deploy dashboard** → Run workflow | A markup, styling or scoring change. Rebuilds `docs/data` from the committed `outputs/` and deploys. Touches no API and costs nothing. |
| Wait for the 09:00 UTC daily run | A content change — it regenerates the digest anyway. |
| `cd docs && vercel deploy --prod` | Local, when you already have the CLI logged in. |

`deploy-dashboard.yml` exists because the daily run spends real Anthropic and
SerpAPI money to regenerate a digest, and a CSS change needs none of that.

The `.vercel` link file lives in `docs/` and is gitignored, so a fresh clone has
no project link — the CLI will ask, or you can write
`docs/.vercel/project.json` with the `orgId` and `projectId` from
`daily-digest.yml`.

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

Python 3.11 or newer (the workflow pins 3.11).

```bash
pip install -r requirements.txt pytest
python3 -m pytest tests/ -q      # no API key needed; the suite touches no network

export ANTHROPIC_API_KEY=...
export NCBI_API_KEY=...        # optional — raises PubMed rate limit from 3 to 10 req/sec
export SERPAPI_API_KEY=...     # optional — enables the prior-coverage check
cd scripts
python3 main.py
```

**Rebuilding the dashboard does not need a key or a pipeline run.** Scores, tags
and coverage state are all recomputed from what is already on disk:

```bash
cd scripts && python3 build_dashboard_data.py
```

Node is needed only for `tests/test_dashboard.py`'s render check, which executes
the dashboard's inline script; the test skips itself if Node is absent.

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
  candidate list.

  **This secret was missing from the daily workflow's `env:` block until
  2026-09-05**, and Actions only puts a secret in the environment if the step
  names it — so the coverage check had never run on a scheduled digest. Expect up
  to ~20 Google News searches on the first few runs while the cache fills, then
  far fewer, plus a weekly Trends batch of about 6.

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
  llm.py                   the one place this pipeline talks to Claude
  digest_generator.py      Claude prompt + schema that produces the study records
  digest_render.py         renders those records into the digest markdown
  fact_checker.py          Claude prompt + schema that produces the verdict records
  factcheck_render.py      renders those records into the fact-check report
  scoring.py               deterministic 0-100 study score and band
  trends.py                Claude prompt + call for trends/feature-pitch + topic memory
  outlets.py               pitch targets from the publisher registry, clinical-topic matching
  web_coverage.py          Google News check — has the press already run these studies?
  topic_demand.py          weekly Google Trends report on the focus rotation
  build_dashboard_data.py  parses outputs/*.md into docs/data/index.json + runs/
outputs/                   every digest + fact-check ever generated (.md + .coverage.json)
topic_memory/              per-topic running memory used by trends.py
state/                     SerpAPI coverage cache — committed, the runner does not persist
docs/                      static dashboard (index.html + data/), deployed to Vercel
config/digest_config.json  audience and rotation settings
config/media/              publisher registries, exported from the AgingWire workbooks
tests/                     pipeline, scoring, render round-trip and dashboard tests
.github/workflows/         daily cron (daily-digest.yml), weekly topic demand (topic-demand.yml)
.gitignore                 keeps the local Vercel CLI link dir (.vercel) untracked
```

## The model returns records

The digest used to be markdown the model wrote, which `build_dashboard_data.py`
then regex-scraped back into fields. That coupling caused real damage: the
fact-checker started writing `## Study N:` where the verdict regex expected
`### Study N:`, and 22 of 52 reports silently lost every verdict — half the
archive rendered with no fact-check badge, under a green pipeline.

So the model returns **records** (`output_config.format` with a JSON schema) and
Python renders the markdown. The heading level is no longer its to choose.

- The rendered templates are byte-compatible with what the model used to produce,
  so the parser reads new files and the 105 archived ones the same way.
- `tests/test_render_roundtrip.py` renders records, parses them back and compares
  field by field. That is the assertion that keeps the renderer and the parser
  from drifting apart.
- **The continuation retry does not survive this.** Half a JSON array cannot be
  repaired by concatenating the next turn the way half a paragraph can, so
  `llm.complete_json` raises and the input is batched instead — 12 abstracts per
  digest call, 10 studies per fact-check call. `trends.py` still returns prose and
  keeps the retry.
- A PMID the model invented is dropped in both steps, and a declined batch loses
  only its own studies rather than the run.

## How a study is scored

`scripts/scoring.py` gives every study a 0-100 score and one of four bands, from
data the pipeline already holds. Nothing is asked of a model: a score a model
assigns cannot be reproduced on a re-run of the same abstract and cannot be
unit-tested.

| Component | Weight | 5 means |
| --- | --- | --- |
| `evidence_type` | 3 | meta-analysis, systematic review or randomized trial |
| `coverage_gap` | 3 | checked, and nobody has covered it |
| `journal_tier` | 2 | a top-tier general medical or flagship gerontology title |
| `recency` | 2 | published within the last month |
| `sample_size` | 1 | 10,000+ participants |
| `accuracy` | 1 | fact-check cleared with no issues |

Two things that took tuning against the real 1,122 studies:

- **A component nobody measured is dropped from the score, not scored as a
  middling 2.** Coverage was never actually checked before 2026-09-05, so folding
  "we didn't look" in as a mid value would have jumped every study about 15 points
  the day the check was switched on. Scores stay comparable across that boundary.
- **The first thresholds put 53% of the archive in one band**, which filters
  nothing. Retuned to roughly 14 / 27 / 37 / 20%.

Bands, not ranks: two studies a few points apart are not meaningfully different.
The score ranks *pitchability*, not scientific quality — a careful small study can
score below a weaker large one because more readers can be reached with it.

Re-scoring the whole archive is a dashboard rebuild, with no API calls.

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

**Terms are split into specific and general, and only a specific hit earns the
top band.** Several topics' term lists were once made entirely of words nearly
every publication in both registries uses — `sleep` was `["health", "wellness",
"aging"]` — so every outlet landed in the top band and the suggestion degraded to
"any generalist" on every clinical run. The split is what makes the results
differ by topic: Being Patient for dementia, Hospice News for palliative care,
Food Management for nutrition, women's and fitness titles for osteoporosis.

Focus keys match on whole words with a plural stem, so "sleep quality" reaches
sleep and "fall" reaches falls, but "care" no longer resolves to "palliative
care". A missing or unreadable CSV raises rather than returning an empty list —
it used to produce a run with no pitch targets and no error.

## Has the press already run it?

`scripts/web_coverage.py` asks Google News whether each study has already been
written up. Every outlet it finds is excluded from the pitch suggestions —
pitching a story to the publication that just ran it is the one suggestion
guaranteed to be wrong — and the result becomes the study's coverage state,
which feeds both the score and the dashboard's Coverage facet.

Google ranks by topical relevance, so results are filtered on headline overlap
with the study title; without that gate a grip-strength study matches articles
about grip strengtheners for climbers.

**Every study is checked, and results are cached by PMID** in
`state/coverage_cache.json` with a 14-day TTL. It used to check only the first 8
of a run averaging 21.6, leaving most studies with no signal. The PubMed window
is 90 days wide and runs are daily, so the same study comes round repeatedly and
used to cost a fresh lookup each time; after the first pass most runs are mostly
cache hits. **The cache is committed, not ignored** — the Actions runner
filesystem does not persist.

Calls are paced 0.4s apart and a run cannot make more than 40 lookups. A failed
lookup is counted as skipped rather than silently dropped: "no coverage found"
and "we never looked" are different claims and the dashboard distinguishes them.

Requires `SERPAPI_API_KEY`; without it the check is skipped, the run says so, and
the pitch keeps the full candidate list.

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

