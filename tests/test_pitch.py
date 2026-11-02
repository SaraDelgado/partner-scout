import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "execution"))
import pitch

BRIEF = {
    "sender": "Sara", "offer": "a programme", "looking_for": "specialists", "language": "Spanish",
    "criteria": [{"name": "fit", "weight": 1, "description": "fits"}],
}
RECORD = {"name": "Centro A", "slug": "centro-a", "status": "ok", "dossier": {"facts": [
    {"id": "f1", "claim": "Community of 45,000 older adults", "source_url": "https://a.example/", "date": ""}]}}
RED = {"name": "Centro A", "slug": "centro-a", "objections": [
    {"objection": "Minor doubt", "severity": 1, "addressable": True, "how_to_address": "x",
     "grounded_in": "none", "fact_ids": []},
    {"objection": "No signed residence", "severity": 3, "addressable": True, "how_to_address": "Get a letter",
     "grounded_in": "brief", "fact_ids": []},
]}


def body(**changes):
    p = {
        "one_pager": {"title": "Piloto", "partner_goal": "Crecer", "they_get": ["Crédito"], "we_get": ["Sesiones"],
                      "pilot": {"scope": "Un grupo", "duration": "4 semanas", "success_measure": "Asistencia"},
                      "next_step": "Llamada"},
        "outreach": {"subject": "Hola", "body": "Su comunidad de 45,000 personas mayores me inspiró."},
        "follow_up": "Le escribo de nuevo.",
        "fact_ids_used": ["f1"],
        "objection_addressed": 2,
    }
    p.update(changes)
    return p


def reply(payload, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=json.dumps(payload))])


class FakeClient:
    def __init__(self, *responses):
        self.calls, self.responses = [], list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def row(verdict="reframe", override=""):
    r = {"name": "Centro A", "slug": "centro-a", "verdict": verdict, "override": override, "outcome": ""}
    return {**r, "effective": pitch.effective_verdict(r)}


@pytest.mark.parametrize("verdict,override,expected", [
    ("reframe", "", "reframe"),
    ("drop", "go: they asked for a call", "go"),
    ("go", "Drop", "drop"),
    ("go", "maybe later", "invalid_override"),
])
def test_override_wins(verdict, override, expected):
    assert pitch.effective_verdict({"verdict": verdict, "override": override}) == expected


def test_top_index_matches_red_team():
    assert pitch.top_index(RED["objections"]) == 2


def test_valid_pitch_has_no_notes():
    assert pitch.validate_pitch(body(), row(), RECORD, RED, BRIEF) == []


@pytest.mark.parametrize("changes", [{"fact_ids_used": ["f9"]}, {"objection_addressed": 1}])
def test_untrustworthy_pitch_is_rejected(changes):
    with pytest.raises(ValueError):
        pitch.validate_pitch(body(**changes), row(), RECORD, RED, BRIEF)


def test_go_does_not_need_an_objection():
    assert pitch.validate_pitch(body(objection_addressed=0), row("go"), RECORD, RED, BRIEF) == []


def test_reviewer_notes_for_length_and_unsourced_numbers():
    long_body = "palabra " * 151 + "con 300 residentes"
    notes = pitch.validate_pitch(body(outreach={"subject": "s", "body": long_body}, follow_up="x " * 61,
                                      one_pager={**body()["one_pager"], "they_get": ["a", "b", "c", "d"]}),
                                 row(), RECORD, RED, BRIEF)
    assert len(notes) == 4 and any("300" in n for n in notes)


def make_run(tmp_path, verdicts):
    (tmp_path / "dossiers").mkdir()
    (tmp_path / "red_team").mkdir()
    (tmp_path / "verdicts.csv").write_text("name,slug,verdict,top_objection,override,outcome\n" + verdicts,
                                           encoding="utf-8-sig")
    for name in ("centro-a", "centro-b"):
        (tmp_path / "dossiers" / f"{name}.json").write_text(json.dumps(RECORD))
        (tmp_path / "red_team" / f"{name}.json").write_text(json.dumps(RED))


def test_load_partners_skips_drop(tmp_path):
    make_run(tmp_path, "Centro A,centro-a,reframe,x,,\nCentro B,centro-b,drop,x,,\n")
    partners, skipped = pitch.load_partners(tmp_path)
    assert [p[0]["name"] for p in partners] == ["Centro A"]
    assert skipped == [("Centro B", "drop")]


def test_process_writes_markdown_and_caches(tmp_path):
    make_run(tmp_path, "Centro A,centro-a,reframe,x,,\n")
    partners, _ = pitch.load_partners(tmp_path)
    r, record, red = partners[0]
    client = FakeClient(reply(body()))
    result = pitch.process(client, BRIEF, r, record, red, tmp_path / "cache")
    assert result["status"] == "ok" and client.calls[0]["model"] == "claude-opus-5-5"
    assert pitch.process(FakeClient(), BRIEF, r, record, red, tmp_path / "cache") == result
    pitch.write_outputs([result], partners, tmp_path)
    md = (tmp_path / "pitches" / "centro-a.md").read_text()
    assert "nothing has been sent" in md and "No signed residence" in md and "https://a.example/" in md


@pytest.mark.parametrize("response,status", [
    (reply(body(), stop_reason="refusal"), "model_refused"),
    (reply(body(objection_addressed=1)), "invalid_output"),
])
def test_unusable_replies_are_flagged(tmp_path, response, status):
    result = pitch.process(FakeClient(response), BRIEF, row(), RECORD, RED, tmp_path)
    assert result["status"] == status and result["pitch"] is None
