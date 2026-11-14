"""API and Bearer auth tests for Baiosfera Knowledge Hub."""

from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.main import app


class FakeStore:
    def stats(self):
        return {"collection": "baiosfera_knowledge", "exists": True, "points_count": 42}

    def search(self, query, limit=8, academia=None, curso=None, disciplina=None, tipo=None):
        return [
            {
                "score": 0.91,
                "title": "Category of One",
                "text": f"Match for {query}",
                "academia": academia or "VELOCITYMEDIA",
                "curso": curso or "INFLUENCE",
                "disciplina": disciplina or "posicionamiento",
                "tipo": tipo or "playbook",
                "path": "03_PLAYBOOKS_MAESTROS/00_category_of_one.md",
            }
        ]

    def upsert_chunks(self, chunks):
        return len(chunks)


def _patch_auth_and_store(monkeypatch, token="secret-test-token"):
    settings = SimpleNamespace(knowledge_bearer_token=token)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_store", lambda: FakeStore())


def test_health_is_public():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_endpoints_reject_missing_or_wrong_bearer(monkeypatch):
    _patch_auth_and_store(monkeypatch)
    client = TestClient(app)

    assert client.get("/v1/stats").status_code == 401
    assert client.post("/v1/search", json={"query": "oferta"}).status_code == 401
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    assert (
        client.get("/v1/stats", headers={"Authorization": "Bearer wrong-token"}).status_code
        == 401
    )


def test_protected_endpoints_accept_valid_bearer(monkeypatch):
    _patch_auth_and_store(monkeypatch)
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret-test-token"}

    stats_resp = client.get("/v1/stats", headers=headers)
    assert stats_resp.status_code == 200
    assert stats_resp.json()["points_count"] == 42

    search_resp = client.post("/v1/search", json={"query": "categoria de uno"}, headers=headers)
    assert search_resp.status_code == 200
    assert search_resp.json()["count"] == 1
    assert search_resp.json()["results"][0]["title"] == "Category of One"
