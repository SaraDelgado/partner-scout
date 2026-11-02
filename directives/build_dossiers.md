# Directive: Build partner dossiers

**Goal:** for each shortlisted partner, a one-page brief of who they are, what they want, what each side could gain and what is still unknown, with every fact tied to a public source.

**Inputs**
- `brief.json`, the same file Scout used.
- `.tmp/run/ranked.csv` and the shortlist: `--names "A,B"` or `--top N` (ranked rows with status `ok` only).

**Tool:** `execution/dossier.py`

**What the tool does**
1. Reads up to 5 pages of the partner's own site: home, about, services, press or news, and contact.
2. Runs a capped web search for recent public signals: news, openings, funding, ownership changes, awards, events. The default is 5 searches per partner.
3. Asks the model for the dossier as structured output (schema below).
4. Validates in code: every fact has a source URL that the tool actually retrieved, every date has the form `YYYY-MM` or `YYYY-MM-DD`, and every required section exists. A fact without a retrieved source is moved to `open_questions`, not dropped silently.
5. Writes `dossiers/<slug>.json` and a readable `dossiers/<slug>.md`.

**Dossier schema**
- `facts`: list of `{id, claim, source_url, date}`. Later steps can cite only these ids.
- `overview`: what they do and for whom, in 2 or 3 sentences, citing fact ids.
- `their_goals`: what they appear to be trying to achieve now (growth, new markets, filling capacity, reputation), each citing fact ids.
- `value_exchange`: `{we_give, we_get}` with concrete items.
- `decision_roles`: public job titles likely involved in a partnership decision. Titles only, never personal contact details.
- `recent_signals`: changes from the last 12 months that open or close a door, citing fact ids.
- `open_questions`: what a first call should find out.

**Steps**
1. Run with `--dry-run` to see pages found, searches planned and a rough cost.
2. Get approval for the cost.
3. Run for real.
4. A person reads each `.md`, opens a sample of sources, and deletes any fact that is wrong or out of date.

**Rules**
- Only public business sources. Skip pages that need a login.
- If the sources disagree, keep both facts and add an open question.
- A thin dossier is a finding, not a failure: it usually means the partner has little public presence.

**Known limits**
- Search results can be old or about a different company with a similar name. Check the source behind every key fact.
- Sites that render only with JavaScript yield little text, as with Scout.
- Search results are kept per partner in the cache: a rerun with the same site text reuses them. Delete `.tmp/run/cache/dossier/` to search again.
- To skip Scout, pass a candidates file with `--ranked` and pick partners with `--names`.
