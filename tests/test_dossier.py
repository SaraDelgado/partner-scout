import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "execution"))
import dossier

BRIEF = {
    "sender": "Sara", "offer": "a programme", "looking_for": "specialists", "language": "Spanish",
    "criteria": [{"name": "fit", "weight": 1, "description": "fits"}],
}
NEWS = "https://news.example/article"


def text(t):
    return SimpleNamespace(type="text", text=t, citations=None)


def search_reply(stop_reason="end_turn"):
    result = SimpleNamespace(type="web_search_tool_result",
                             content=[SimpleNamespace(type="web_search_result", url=NEWS)])
    return SimpleNamespace(stop_reason=stop_reason, content=[result, text(f"- Opened a new centre ({NEWS}, 2026-05)")])


def dossier_body(site_url, **changes):
    body = {
        "facts": [
            {"id": "f1", "claim": "Runs music sessions for older adults", "source_url": site_url, "date": ""},
            {"id": "f2", "claim": "Opened a new centre", "source_url": NEWS, "date": "2026-05"},
            {"id": "f3", "claim": "Won an award", "source_url": "https://made-up.example", "date": "May 2026"},
        ],
        "overview": {"text": "Music therapy centre.", "fact_ids": ["f1", "f3"]},
        "their_goals": [{"goal": "Grow into new venues", "fact_ids": ["f2"]},
                        {"goal": "Gain prestige", "fact_ids": ["f3"]}],
        "value_exchange": {"we_give": ["A residence pilot"], "we_get": ["Sessions"]},
        "decision_roles": ["Director", "Ana, ana@centro.example"],
        "recent_signals": [{"signal": "New centre", "fact_ids": ["f2"]}],
        "open_questions": ["Price per session?"],
    }
    body.update(changes)
    return SimpleNamespace(stop_reason="end_turn", content=[text(json.dumps(body))])


class FakeClient:
    def __init__(self, *responses):
        self.calls, self.responses = [], list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text('<body>Centro de musicoterapia<a href="/nosotros.html">Nosotros</a>'
                                     '<a href="/servicios.html">Servicios</a><a href="/tienda.html">Tienda</a></body>')
    (root / "nosotros.html").write_text("Trabajamos con personas mayores")
    (root / "servicios.html").write_text("Sesiones en residencias")
    (root / "tienda.html").write_text("Shop")
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()


def test_slugify():
    assert dossier.slugify("Centro Mexicano de Musicoterapia!") == "centro-mexicano-de-musicoterapia"


def test_shortlist_by_top_and_names(tmp_path):
    ranked = tmp_path / "ranked.csv"
    ranked.write_text("rank,name,website,status\n1,A,https://a.example,ok\n,B,https://b.example,fetch_failed\n"
                      "2,C,https://c.example,ok\n", encoding="utf-8-sig")
    assert [r["name"] for r in dossier.load_shortlist(ranked, top=5)] == ["A", "C"]
    assert [r["name"] for r in dossier.load_shortlist(ranked, names="C, A")] == ["C", "A"]
    with pytest.raises(ValueError):
        dossier.load_shortlist(ranked, names="Z")


def test_fetch_reads_useful_pages_only(site):
    urls = [u for u, _ in dossier.fetch_site_pages(site, allow_private=True)]
    assert len(urls) == 3 and not any("tienda" in u for u in urls)


def test_validation_moves_unsourced_facts_and_strips_contact_details():
    body = json.loads(dossier_body("https://site.example/").content[0].text)
    clean, issues = dossier.validate_dossier(body, {"https://site.example", NEWS})
    assert [f["id"] for f in clean["facts"]] == ["f1", "f2"]
    assert clean["overview"]["fact_ids"] == ["f1"]
    assert [g["goal"] for g in clean["their_goals"]] == ["Grow into new venues"]
    assert clean["decision_roles"] == ["Director"]
    assert any("Won an award" in q for q in clean["open_questions"])
    assert any("Gain prestige" in q for q in clean["open_questions"])
    assert issues


def test_bad_date_is_blanked():
    body = json.loads(dossier_body("https://s.example").content[0].text)
    body["facts"][0]["date"] = "May 2026"
    clean, _ = dossier.validate_dossier(body, {"https://s.example", NEWS})
    assert clean["facts"][0]["date"] == ""


def test_duplicate_fact_ids_are_rejected():
    body = json.loads(dossier_body("https://s.example").content[0].text)
    body["facts"][1]["id"] = "f1"
    with pytest.raises(ValueError):
        dossier.validate_dossier(body, {"https://s.example"})


def test_process_end_to_end_and_cache(site, tmp_path):
    client = FakeClient(search_reply(), dossier_body(site))
    candidate = {"name": "Centro A", "website": site}
    record = dossier.process(client, BRIEF, candidate, tmp_path / "c", allow_private=True)
    assert record["status"] == "ok"
    assert [f["id"] for f in record["dossier"]["facts"]] == ["f1", "f2"]
    assert client.calls[0]["tools"][0]["max_uses"] == dossier.DEFAULT_SEARCHES
    assert client.calls[1]["model"] == "claude-opus-5-5"
    again = dossier.process(FakeClient(), BRIEF, candidate, tmp_path / "c", allow_private=True)
    assert again["dossier"] == record["dossier"]

    dossier.write_outputs([record], tmp_path / "out")
    md = (tmp_path / "out" / "dossiers" / "centro-a.md").read_text()
    assert NEWS in md and "Draft for review" in md


def test_no_searches_makes_one_call(site, tmp_path):
    client = FakeClient(dossier_body(site, facts=[], overview={"text": "x", "fact_ids": []},
                                     their_goals=[], recent_signals=[]))
    record = dossier.process(client, BRIEF, {"name": "A", "website": site}, tmp_path, searches=0,
                             allow_private=True)
    assert record["status"] == "ok" and len(client.calls) == 1 and "tools" not in client.calls[0]


def test_paused_search_is_resumed(site, tmp_path):
    client = FakeClient(search_reply("pause_turn"), search_reply(), dossier_body(site))
    record = dossier.process(client, BRIEF, {"name": "A", "website": site}, tmp_path, allow_private=True)
    assert record["status"] == "ok" and len(client.calls) == 3
    assert client.calls[1]["messages"][1]["role"] == "assistant"


@pytest.mark.parametrize("reply,status", [
    (SimpleNamespace(stop_reason="refusal", content=[]), "model_refused"),
    (SimpleNamespace(stop_reason="end_turn", content=[text("not json")]), "invalid_output"),
])
def test_unusable_replies_are_flagged(site, tmp_path, reply, status):
    record = dossier.process(FakeClient(search_reply(), reply), BRIEF, {"name": "A", "website": site}, tmp_path,
                             allow_private=True)
    assert record["status"] == status and record["dossier"] is None
