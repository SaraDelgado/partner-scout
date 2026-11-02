# partner-scout

Give it a list of possible partners and what you're looking for. It reads each company's public website, ranks the list against your criteria with evidence, and drafts a first message for you to review.

**It never sends anything.** You decide who to contact and what to say.

I built it to find partners for [One Day Trip Mexico City](https://www.instagram.com/onedaytripmexicocity/), but the criteria are yours to change, so it works for any partnership search.

## How it works

| Layer | Where | Job |
|---|---|---|
| Directive | `directives/` | The plain-language procedure |
| Orchestration | You, or an AI agent | Decide what to run and handle exceptions |
| Execution | `execution/` | Fetch pages, compute scores, write files |

Claude rates each criterion from 0 to 5 and has to cite evidence from the site. The score itself is computed in code from your weights, so the ranking stays explainable.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Add your Anthropic API key to `.env`, then copy `examples/odt/` and edit the brief and candidates. Check sites and rough cost first, with no API calls:

```bash
.venv/bin/python execution/scout.py --brief examples/odt/brief.json --candidates examples/odt/candidates.csv --dry-run
```

Then run it:

```bash
set -a; source .env; set +a
.venv/bin/python execution/scout.py --brief examples/odt/brief.json --candidates examples/odt/candidates.csv
```

Results land in `.tmp/run/`: `ranked.csv` and `drafts.md`.

### Step 2: dossiers for your shortlist

Pick the partners worth a closer look, by name or as the top N, and build a dossier for each. It reads up to 5 pages of their site and runs up to 5 web searches per partner (`--searches 0` turns search off):

```bash
.venv/bin/python execution/dossier.py --brief examples/odt/brief.json --top 3 --dry-run
.venv/bin/python execution/dossier.py --brief examples/odt/brief.json --top 3
```

Each partner gets `.tmp/run/dossiers/<name>.md`: overview, what they appear to want, recent signals, value exchange, open questions, and every fact with its source. A fact whose source was not actually retrieved is moved to open questions instead of being shown as true.

### Step 3: red team each dossier

Before reaching out, an agent argues the partner's side: the strongest reasons they would say no, how serious each is, and whether a change in your offer could fix it. Code, not the model, turns that into a verdict: `drop` if something would end the deal and cannot be fixed, `reframe` if a serious objection can be fixed, `go` otherwise.

```bash
.venv/bin/python execution/red_team.py --brief examples/odt/brief.json --dry-run
.venv/bin/python execution/red_team.py --brief examples/odt/brief.json
```

Read `.tmp/run/red_team/<name>.md`. Verdicts collect in `.tmp/run/verdicts.csv`, where you can override one and record what happened after outreach.

### Step 4: draft the pitch

For every partner marked `go` or `reframe`, it drafts a one-pager, an outreach message that answers the top objection, and a follow-up for a week later, in your brief's language. A pitch that cites a fact not in the dossier, or that dodges the top objection, is rejected.

```bash
.venv/bin/python execution/pitch.py --brief examples/odt/brief.json --dry-run
.venv/bin/python execution/pitch.py --brief examples/odt/brief.json
```

Read `.tmp/run/pitches/<name>.md`, check the facts and the "Check before sending" list, then edit and send it yourself.

## The pipeline: from shortlist to pitch

Scouting is step one of a partnerships pipeline. Every agent has a directive in `directives/`. All four are built.

| Step | Agent | What it adds |
|---|---|---|
| 1 | Scout (built) | Ranked shortlist with evidence |
| 2 | Dossier (built) | Goals, recent signals and value exchange for each partner, every fact with a source |
| 3 | Red team (built) | The strongest reasons they would say no, and a verdict of `go`, `reframe` or `drop` computed in code |
| 4 | Pitch (built) | One-pager, outreach that answers the top objection, and a follow-up |

A person approves the shortlist, every paid run and every message. See `directives/partnerships_pipeline.md`.

## Limits

- Sites that only render with JavaScript give it little to read.
- Scout reads the homepage and one About/Contact page; Dossier reads up to 5 pages.
- A low score can mean the site says little, not that the business is a poor fit.
- Drafts can contain mistakes, so check every fact before sending.

## Tests

```bash
.venv/bin/python -m pytest
```

## License

MIT
