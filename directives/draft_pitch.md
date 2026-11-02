# Directive: Draft the pitch

**Goal:** for each partner marked `go` or `reframe`, a short one-pager of what each side gains and an outreach message that answers their strongest objection. A person reviews and sends.

**Inputs**
- `brief.json`
- `.tmp/run/dossiers/<slug>.json`
- `.tmp/run/red_team/<slug>.json` and `.tmp/run/verdicts.csv`. The tool uses `override` when it is filled, `verdict` otherwise, and skips `drop`. An override starts with the verdict and may add a reason after a colon, such as `go: they asked for a call`.

**Tool:** `execution/pitch.py` (by default every `go` or `reframe` partner; `--names "A,B"` to pick)

**What the tool does**
1. Gets structured output from the model:
   - `one_pager`: title, the partner's goal in one line, what they get (3 points at most), what we get, a proposed first pilot (scope, duration, success measure), and the next step.
   - `outreach`: a subject line and a body under 150 words in the brief's `language`.
   - `follow_up`: a message under 60 words for 7 days later with no reply.
   - `fact_ids_used`: every dossier fact the text relies on.
   - `objection_addressed`: the number of the red team objection the outreach answers, or 0 for `go`.
2. Validates in code. It rejects the pitch as `invalid_output` if it cites a fact id that is not in the dossier, or if a `reframe` pitch does not answer the top objection. It lists under "Check before sending" any text over the word limits, more than 3 points in what they get, and numbers of two or more digits that appear in neither the dossier nor the brief.
3. Writes `pitches/<slug>.md`: the one-pager, the outreach, the follow-up, and the sources of every cited fact at the end, so the reviewer can check them.

**Steps**
1. Run with `--dry-run`, then get approval for the cost.
2. Run for real.
3. A person checks each fact against its source, edits the tone and sends it from their own account.
4. Record the outcome in `verdicts.csv`.

**Rules**
- Never send anything automatically.
- No invented numbers, prices, clients or shared contacts. If the pitch needs a number that the dossier does not have, it says so as a question.
- The pilot asks for little: one small group, a set duration, one clear measure of success. No dates: the model cannot know your calendar.
- The Pitch draft replaces Scout's first-message draft for this partner. Scout's draft was written before the dossier and red team existed.
