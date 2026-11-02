import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "execution"))
import red_team

BRIEF = {
    "sender": "Sara", "offer": "a programme", "looking_for": "specialists", "language": "Spanish",
    "criteria": [{"name": "fit", "weight": 1, "description": "fits"}],
}
RECORD = {"name": "Centro A", "slug": "centro-a", "status": "ok",
          "dossier": {"facts": [{"id": "f1", "claim": "Avoids residences", "source_url": "https://a.example",
                                 "date": ""}]}}


def objection(severity=2, addressable=True, grounded_in="dossier", fact_ids=("f1",), text="They avoid residences"):
    return {"objection": text, "severity": severity, "addressable": addressable, "how_to_address": "Reframe",
            "grounded_in": grounded_in, "fact_ids": list(fact_ids)}


def reply(objections, stop_reason="end_turn"):
    body = json.dumps({"objections": objections})
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=body)])


class FakeClient:
    def __init__(self, *responses):
        self.calls, self.responses = [], list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.parametrize("objections,expected", [
    ([], "go"),
    ([objection(severity=1, addressable=False)], "go"),
    ([objection(severity=2, addressable=False)], "go"),
    ([objection(severity=2)], "reframe"),
    ([objection(severity=3)], "reframe"),
    ([objection(severity=2), objection(severity=3, addressable=False)], "drop"),
])
def test_verdict_rules(objections, expected):
    assert red_team.verdict(objections) == expected


def test_ungrounded_objection_is_lowered_to_severity_1():
    out, issues = red_team.validate_objections(
        [objection(severity=3, addressable=False, grounded_in="none", fact_ids=())], RECORD["dossier"])
    assert out[0]["severity"] == 1 and issues
    assert red_team.verdict(out) == "go"


def test_unknown_fact_ids_are_removed_and_can_remove_grounding():
    out, issues = red_team.validate_objections([objection(severity=3, fact_ids=("f9",))], RECORD["dossier"])
    assert out[0]["fact_ids"] == [] and out[0]["severity"] == 1 and issues


def test_brief_grounding_keeps_severity():
    out, issues = red_team.validate_objections([objection(severity=3, grounded_in="brief", fact_ids=())],
                                               RECORD["dossier"])
    assert out[0]["severity"] == 3 and not issues


@pytest.mark.parametrize("objections", [[objection(severity=4)], [objection()] * 6])
def test_unusable_objections_are_rejected(objections):
    with pytest.raises(ValueError):
        red_team.validate_objections(objections, RECORD["dossier"])


def test_top_objection_prefers_severe_and_unfixable():
    objections = [objection(severity=3, text="fixable"), objection(severity=3, addressable=False, text="blocker"),
                  objection(severity=1, text="minor")]
    assert red_team.top_objection(objections) == "blocker"


def test_process_and_cache(tmp_path):
    client = FakeClient(reply([objection(severity=3, addressable=False)]))
    result = red_team.process(client, BRIEF, RECORD, tmp_path)
    assert (result["status"], result["verdict"]) == ("ok", "drop")
    assert client.calls[0]["model"] == "claude-opus-5-5"
    assert red_team.process(FakeClient(), BRIEF, RECORD, tmp_path) == result


@pytest.mark.parametrize("response,status", [
    (reply([], stop_reason="refusal"), "model_refused"),
    (reply([objection(severity=0)]), "invalid_output"),
    (SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="no")]), "invalid_output"),
])
def test_unusable_replies_are_flagged(tmp_path, response, status):
    result = red_team.process(FakeClient(response), BRIEF, RECORD, tmp_path)
    assert result["status"] == status and result["verdict"] == ""


def test_verdicts_keep_human_override_and_outcome(tmp_path):
    (tmp_path / "verdicts.csv").write_text("name,slug,verdict,top_objection,override,outcome\n"
                                           "Centro A,centro-a,drop,old,go: they agreed on a call,meeting\n",
                                           encoding="utf-8-sig")
    result = {"name": "Centro A", "slug": "centro-a", "status": "ok", "verdict": "reframe",
              "objections": [objection()], "issues": []}
    red_team.write_outputs([result], tmp_path)
    with open(tmp_path / "verdicts.csv", encoding="utf-8-sig") as f:
        row = next(csv.DictReader(f))
    assert row["verdict"] == "reframe" and row["override"] == "go: they agreed on a call"
    assert row["outcome"] == "meeting"
    assert "Verdict: reframe" in (tmp_path / "red_team" / "centro-a.md").read_text()


def test_load_dossiers_skips_failed_and_finds_by_name(tmp_path):
    folder = tmp_path / "dossiers"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps({**RECORD, "name": "A"}))
    (folder / "b.json").write_text(json.dumps({**RECORD, "name": "B", "status": "invalid_output"}))
    assert [r["name"] for r in red_team.load_dossiers(tmp_path)] == ["A"]
    with pytest.raises(ValueError):
        red_team.load_dossiers(tmp_path, names="B")
