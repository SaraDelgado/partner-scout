# Directive: Red team a partner

**Goal:** before any outreach, argue the partner's side. List the reasons they would say no, judge whether each one can be addressed, and give a verdict of `go`, `reframe` or `drop` that code computes, not the model.

**Inputs**
- `brief.json`
- `.tmp/run/dossiers/<slug>.json` from the Dossier step.

**Tool:** `execution/red_team.py` (by default every dossier with status `ok`; `--names "A,B"` to pick)

**What the tool does**
1. Gives the model the brief and the dossier, and asks it to answer as the partner's decision maker.
2. Gets up to 5 objections as structured output: `{objection, severity, addressable, how_to_address, grounded_in, fact_ids}`. `grounded_in` is `dossier`, `brief` or `none`.
   - `severity`: 1 is a minor doubt, 2 would slow the deal, 3 would end it.
   - `addressable`: whether a change in our offer or framing could fix it.
3. Validates in code: severity is 1, 2 or 3, and there are at most 5 objections, otherwise the partner is flagged `invalid_output`. Unknown fact ids are removed. An objection with no grounding left is lowered to severity 1 and noted.
4. Computes the verdict in code:
   - `drop`: at least one objection with severity 3 that is not addressable.
   - `reframe`: otherwise, at least one objection with severity 2 or 3 that is addressable.
   - `go`: everything else.
5. Writes `red_team/<slug>.json` and a readable `red_team/<slug>.md`, and adds or updates the partner's row in `verdicts.csv`: `name`, `slug`, `verdict`, `top_objection`, `override`, `outcome`. A rerun never erases `override` or `outcome`.

**Steps**
1. Run with `--dry-run`, then get approval for the cost.
2. Run for real.
3. A person reviews each verdict. To override one, fill `override` in `verdicts.csv` with the new verdict and a short reason. Pitch reads `override` before `verdict`.

**Rules**
- Objections must be grounded in the dossier or in the brief. An objection with no grounding is allowed only at severity 1.
- The red team does not soften its view. Its job is to find the strongest reason for a no.
- Do not drop a partner only because the dossier is thin. That is an open question, not an objection.
