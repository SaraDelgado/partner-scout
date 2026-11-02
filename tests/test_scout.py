import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "execution"))
import scout

BRIEF = {
    "sender": "Sara", "offer": "day trips", "looking_for": "venues", "language": "English",
    "criteria": [
        {"name": "fit", "weight": 3, "description": "fits"},
        {"name": "groups", "weight": 1, "description": "hosts groups"},
    ],
}


def reply(scores=None, stop_reason="end_turn"):
    payload = {"scores": scores if scores is not None else [
        {"criterion": "fit", "score": 5, "evidence": "Historic hacienda"},
        {"criterion": "groups", "score": 0, "evidence": ""},
    ], "summary": "Good fit", "draft_message": "Hello"}
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=json.dumps(payload))])


class FakeClient:
    def __init__(self, response):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.response = response

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture
def site(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><script>var hidden=1</script><body>Historic hacienda'
        '<a href="/contacto.html">Contacto</a><a href="https://other.example/about">x</a></body></html>')
    (tmp_path / "contacto.html").write_text('<a href="mailto:hola@hacienda.example?subject=x">Write</a>Open daily')
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()


def test_weighted_score():
    assert scout.weighted_score(BRIEF, reply_scores(5, 0)) == 75.0


def reply_scores(a, b):
    return [{"criterion": "fit", "score": a, "evidence": ""}, {"criterion": "groups", "score": b, "evidence": ""}]


@pytest.mark.parametrize("scores", [
    [{"criterion": "fit", "score": 5, "evidence": ""}],
    reply_scores(6, 0),
    reply_scores(-1, 0),
    reply_scores(5, 0) + [{"criterion": "fit", "score": 1, "evidence": ""}],
])
def test_bad_scores_are_rejected(scores):
    with pytest.raises(ValueError):
        scout.weighted_score(BRIEF, scores)


def test_fetch_reads_contact_page_and_skips_scripts(site):
    text, emails, truncated = scout.fetch_site(site, allow_private=True)
    assert "Historic hacienda" in text and "Open daily" in text
    assert "hidden" not in text
    assert emails == ["hola@hacienda.example"]
    assert truncated is False


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/", "http://localhost/"])
def test_private_and_non_http_urls_are_blocked(url):
    with pytest.raises(ValueError):
        scout.assert_public_url(url)


def test_process_scores_and_never_reuses_paid_call(site, tmp_path):
    client = FakeClient(reply())
    candidate = {"name": "A", "website": site}
    row = scout.process(client, BRIEF, candidate, tmp_path / "c", allow_private=True)
    assert (row["status"], row["score"]) == ("ok", 75.0)
    assert row["emails"] == "hola@hacienda.example"
    scout.process(client, BRIEF, candidate, tmp_path / "c", allow_private=True)
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == "claude-opus-5-5"


@pytest.mark.parametrize("response,status", [
    (reply(stop_reason="refusal"), "model_refused"),
    (reply(stop_reason="max_tokens"), "output_cut_off"),
    (reply(scores=[{"criterion": "fit", "score": 9, "evidence": ""}]), "invalid_output"),
])
def test_unusable_model_replies_are_flagged(site, tmp_path, response, status):
    row = scout.process(FakeClient(response), BRIEF, {"name": "A", "website": site}, tmp_path, allow_private=True)
    assert row["status"] == status
    assert row["score"] == ""


def test_failed_fetch_makes_no_model_call(tmp_path):
    client = FakeClient(reply())
    row = scout.process(client, BRIEF, {"name": "A", "website": "http://127.0.0.1:9/"}, tmp_path, allow_private=True)
    assert row["status"] == "fetch_failed"
    assert client.calls == []


def test_rank_and_outputs(tmp_path):
    rows = scout.rank([
        {"name": "Low", "status": "ok", "score": 20, "website": "w", "emails": "", "summary": "s", "draft_message": "d"},
        {"name": "Broken", "status": "fetch_failed", "score": "", "website": "w", "emails": "", "summary": "", "draft_message": ""},
        {"name": "High", "status": "ok", "score": 90, "website": "w", "emails": "", "summary": "s", "draft_message": "d"},
    ])
    assert [r["name"] for r in rows] == ["High", "Low", "Broken"]
    scout.write_outputs(rows, tmp_path)
    drafts = (tmp_path / "drafts.md").read_text()
    assert "Nothing here has been sent" in drafts and "Broken" not in drafts
    assert "High" in (tmp_path / "ranked.csv").read_text(encoding="utf-8-sig")


def test_brief_requires_positive_weights(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({**BRIEF, "criteria": [{"name": "x", "description": "y", "weight": 0}]}))
    with pytest.raises(ValueError):
        scout.load_brief(p)
