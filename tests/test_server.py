from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from textchef.server.app import create_app


@pytest.fixture(scope="module")
def client(cfg, tmp_path_factory) -> TestClient:
    web = tmp_path_factory.mktemp("web")
    (web / "index.html").write_text("<!doctype html><title>t</title>")
    (web.parent / "secret.txt").write_text("secret")
    return TestClient(create_app(cfg, web_dir=web))


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert {"ready", "n_rows", "n_topics", "model", "has_id", "has_group",
            "group_label", "theme_light", "theme_dark"} <= set(r.json())


def test_themes(client):
    r = client.get("/api/themes")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["themes"]}
    assert {"cafe", "light", "dark", "blueprint"} <= names
    assert {"colors", "graph", "strings", "font", "scheme"} <= set(r.json()["themes"][0])


def test_graph(client):
    r = client.get("/api/graph")
    assert r.status_code == 200
    body = r.json()
    assert {"topics", "edges", "macro_labels", "points"} <= set(body)
    assert {"id", "label", "count", "macro", "x", "y"} <= set(body["topics"][0])


def test_facets(client):
    r = client.post("/api/facets", json={})
    assert r.status_code == 200
    body = r.json()
    assert {"n", "facets", "topics"} <= set(body)
    first = body["facets"]["group"]["values"][0]["v"]
    scoped = client.post("/api/facets", json={"scope": {"groups": [first]}}).json()
    assert 0 < scoped["n"] < body["n"]


def test_query(client):
    r = client.post("/api/query", json={"q": "manager", "k": 5, "min_score": 0.05})
    assert r.status_code == 200
    body = r.json()
    assert {"method", "terms", "results", "total_matched", "n_in_scope", "topic_hits"} <= set(body)
    assert body["results"]
    assert {"row", "id", "n_id", "text", "score", "topic", "group", "facets", "n_same", "url",
            "credit"} <= set(body["results"][0])


def test_query_with_filters(client):
    scope = {"filters": {"year": {"min": 2019, "max": 2019}, "date": {"min": "2019-01-01"}}}
    r = client.post("/api/query", json={"q": "manager", "min_score": 0.05, "scope": scope})
    assert r.status_code == 200
    assert r.json()["results"]
    assert all(h["facets"]["year"] == 2019 for h in r.json()["results"])


def test_similar_random_browse(client):
    r = client.post("/api/similar", json={"row": 0, "k": 3})
    assert r.status_code == 200 and len(r.json()["results"]) == 3
    assert {"source", "results"} <= set(r.json())
    r = client.post("/api/random", json={"n": 4, "seed": 1})
    assert r.status_code == 200 and len(r.json()["results"]) == 4
    r = client.post("/api/browse", json={"offset": 10, "limit": 5})
    assert r.status_code == 200 and len(r.json()["results"]) == 5
    assert {"results", "total", "offset"} <= set(r.json())
    assert client.post("/api/similar", json={"row": 10**9}).status_code == 404


def test_topic(client):
    r = client.post("/api/topic/0", json={})
    assert r.status_code == 200
    assert {"id", "label", "keywords", "count", "neighbours", "breakdown", "results"} <= set(r.json())
    assert client.post("/api/topic/99999", json={}).status_code == 404


def test_contrast(client):
    groups = client.post("/api/facets", json={}).json()["facets"]["group"]["values"]
    r = client.post("/api/contrast", json={"a": {"groups": [groups[0]["v"]]}})
    assert r.status_code == 200
    assert {"n_a", "n_b", "words_a", "words_b", "lift", "too_few"} <= set(r.json())


def test_document(client):
    r = client.get("/api/document/0")
    assert r.status_code == 200
    assert {"id", "n", "results"} <= set(r.json())


def test_browse_shows_each_text_once(client):
    body = client.post("/api/browse", json={"limit": 200}).json()
    texts = [h["text"] for h in body["results"]]
    assert len(texts) == len(set(texts)) == body["total"]


def test_security_headers(client):
    for path in ("/", "/api/status"):
        h = client.get(path).headers
        assert "default-src 'none'" in h["content-security-policy"]
        assert "unsafe-inline" not in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "no-referrer"


def test_unknown_facet_is_rejected(client):
    scope = {"filters": {"no_such_facet": ["x"]}}
    for path, body in (("/api/query", {"q": "manager", "scope": scope}),
                       ("/api/browse", {"scope": scope}),
                       ("/api/contrast", {"a": scope})):
        assert client.post(path, json=body).status_code == 422
    assert client.post("/api/query", json={"q": "x", "unknown_key": 1}).status_code == 422


def test_path_traversal_is_rejected(client):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt",
                 "/api/document/..%2f..%2fetc%2fpasswd", "/api/topic/../../etc/passwd"):
        r = client.get(path)
        assert r.status_code in (404, 405, 422), path
        assert "secret" not in r.text


def test_foreign_host_header_is_rejected(client):
    assert client.get("/api/status", headers={"host": "example.com"}).status_code == 400
