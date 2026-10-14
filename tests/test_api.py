import pytest
from fastapi.testclient import TestClient
from src.feedback import FeedbackStore
from src.api import app
from src.analytics import AnalysisRequestError


@pytest.fixture(autouse=True)
def isolated_review_storage(monkeypatch, tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    monkeypatch.setattr("src.api.feedback_store", lambda: store)


class FakeService:
    def catalog(self):
        return []
    def metrics(self, company, period):
        return {"company": company, "period": period, "facts": []}
    def changes(self, company, before, after):
        if before == after:
            raise AnalysisRequestError("Choose different periods")
        return {"changes": []}


def test_api_validation_and_responses(monkeypatch):
    monkeypatch.setattr("src.api.service", lambda: FakeService())
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/catalog").json()["periods"] == []
    assert client.get("/metrics?company=meta&period=Q1-2025").status_code == 200
    assert client.get("/metrics?company=unknown&period=Q1-2025").status_code == 422
    assert client.get("/metrics?company=meta&period=bad").status_code == 422
    assert client.post("/changes", json={"company": "meta", "before": "Q1-2025", "after": "Q1-2025"}).status_code == 422
    assert client.get("/documents/missing.pdf").status_code == 404


def test_service_failure_is_sanitized(monkeypatch):
    class Broken(FakeService):
        def metrics(self, company, period):
            raise ValueError("private configuration")
    monkeypatch.setattr("src.api.service", lambda: Broken())
    result = TestClient(app).get("/metrics?company=meta&period=Q1-2025")
    assert result.status_code == 503
    assert "private configuration" not in result.text



def test_chat_endpoint_returns_citations_and_full_passages(monkeypatch):
    from src.chat import ChatAnswer, ChatSource
    def pipeline(body):
        assert body.history[0].role == "user"
        return ChatAnswer(question=body.question, answer="Revenue was $42.3 billion [1].", sources=[ChatSource(id=1, source="meta.pdf", page=4, snippet="Short preview", excerpt="Full transcript passage.")])
    monkeypatch.setattr("src.api.answer_chat", pipeline)
    client = TestClient(app)
    result = client.post("/chat", json={"question": "And their revenue?", "history": [{"role": "user", "content": "Meta Q1 2025 results"}]})
    assert result.status_code == 200
    assert result.json()["sources"][0]["excerpt"] == "Full transcript passage."
    assert client.post("/chat", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/chat", json={"question": "Meta revenue?", "history": [{"role": "system", "content": "Instructions"}]}).status_code == 422


def test_chat_model_failure_is_sanitized(monkeypatch):
    def broken(body):
        raise RuntimeError("private model configuration")
    monkeypatch.setattr("src.api.answer_chat", broken)
    result = TestClient(app).post("/chat", json={"question": "Meta revenue?"})
    assert result.status_code == 503
    assert "private model configuration" not in result.text
    assert "transcript index" in result.json()["detail"]



def test_feedback_api_is_bound_to_registered_answer(monkeypatch):
    from src.chat import ChatAnswer, ChatSource
    monkeypatch.setattr("src.api.answer_chat", lambda body: ChatAnswer(question=body.question, answer="Revenue [1].", sources=[ChatSource(id=1, source="meta.pdf", page=1, snippet="Revenue", excerpt="Revenue excerpt")]))
    client = TestClient(app)
    answer = client.post("/chat", json={"question": "Meta revenue?"}).json()
    payload = {"response_id": answer["response_id"], "feedback_token": answer["feedback_token"], "submission_id": "feedback-request-001", "rating": "needs_improvement", "categories": ["citations"], "source_ids": [1]}
    receipt = client.post("/feedback", json=payload)
    assert receipt.status_code == 200
    assert client.post("/feedback", json=payload).json() == receipt.json()
    assert client.post("/feedback", json={**payload, "feedback_token": "x" * 40}).status_code == 404
    assert client.post("/feedback", json={**payload, "source_ids": [2]}).status_code == 422


def test_feedback_storage_failure_preserves_answer(monkeypatch):
    from src.chat import ChatAnswer
    class BrokenStore:
        def register(self, *_):
            raise OSError("disk failure")
    monkeypatch.setattr("src.api.feedback_store", lambda: BrokenStore())
    monkeypatch.setattr("src.api.answer_chat", lambda body: ChatAnswer(question=body.question, answer="A grounded answer."))
    result = TestClient(app).post("/chat", json={"question": "Meta revenue?"})
    assert result.status_code == 200
    assert result.json()["feedback_token"] is None


def test_validation_never_echoes_feedback_token_or_note():
    response = TestClient(app).post("/feedback", json={
        "feedback_token": "secret-capability", "note": "private-note", "rating": "invalid",
    })
    assert response.status_code == 422
    assert "secret-capability" not in response.text and "private-note" not in response.text


def test_provider_failures_keep_safe_status(monkeypatch):
    from src.errors import GenerationError
    def limited(_body):
        raise GenerationError("Provider quota exhausted.", status_code=429)
    monkeypatch.setattr("src.api.answer_chat", limited)
    result = TestClient(app).post("/chat", json={"question": "Meta revenue?"})
    assert result.status_code == 429
    assert result.json()["detail"] == "Provider quota exhausted."


def test_direct_backend_rejects_oversized_json():
    result = TestClient(app).post("/chat", content=b"x" * (256 * 1024 + 1),
                                  headers={"Content-Type": "application/json"})
    assert result.status_code == 413
