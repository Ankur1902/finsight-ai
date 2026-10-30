"""HTTP boundary with sanitized failures and optional Gemini startup warmup."""
from functools import lru_cache
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from .analytics import AnalysisRequestError, AnalyticsService, METRICS
from .config import DATA_DIR, ROOT_DIR
from .chat import ChatAnswer, ChatRequest, answer_chat
from .feedback import FeedbackError, FeedbackReceipt, FeedbackRequest, FeedbackStore
from .errors import GenerationError
from .http_boundary import BoundedJSONBody
from .security import SecurityMiddleware

@asynccontextmanager
async def lifespan(app):
    from .runtime import generator_identity
    if generator_identity().startswith("gemini:") and os.getenv("GEMINI_API_KEY"):
        def warm():
            from .retrieval import get_retriever
            from .llm import get_llm
            get_retriever()
            get_llm()
        try:
            await asyncio.to_thread(warm)
        except Exception as exc:
            # A failed warm-up degrades first-request latency; it must not stop the API.
            logging.getLogger(__name__).error("Warm-up failed: type=%s", type(exc).__name__)
    yield


app = FastAPI(title="Finsight", version="2.2.0", lifespan=lifespan)
app.add_middleware(BoundedJSONBody)
app.add_middleware(SecurityMiddleware)
log = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _error):
    # FastAPI's default errors include input values, including feedback tokens,
    # questions and notes. Do not serialize or log the rejected input.
    return JSONResponse(status_code=422, content={
        "detail": "Invalid request. Check the required fields, allowed values and length limits."
    })


@lru_cache
def service():
    return AnalyticsService()


def run(operation, unavailable_message="Analysis is unavailable. Check backend model configuration and logs, then retry."):
    try:
        return operation()
    except AnalysisRequestError as exc:
        raise HTTPException(422, str(exc)) from exc
    except GenerationError as exc:
        log.warning("Generation failed: status=%s", exc.status_code)
        raise HTTPException(exc.status_code, str(exc)) from None
    except Exception as exc:
        log.error("Research request failed: type=%s", type(exc).__name__)
        raise HTTPException(503, unavailable_message) from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/catalog")
def catalog():
    return run(lambda: {"periods": service().catalog(), "metrics": METRICS})


@app.get("/questions")
def questions():
    from .questions import verified_questions
    return run(verified_questions)


@app.get("/metrics")
def metrics(company: str = Query(pattern="^(meta|microsoft|nvda)$"), period: str = Query(pattern=r"^Q[1-4]-20\d{2}$")):
    return run(lambda: service().metrics(company, period))


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(pattern="^(meta|microsoft|nvda)$")
    before: str = Field(pattern=r"^Q[1-4]-20\d{2}$")
    after: str = Field(pattern=r"^Q[1-4]-20\d{2}$")


@app.post("/changes")
def changes(body: CompareRequest):
    return run(lambda: service().changes(body.company, body.before, body.after))


@app.get("/documents/{filename}")
def document(filename: str):
    try:
        path = (DATA_DIR / filename).resolve()
    except (OSError, ValueError):
        raise HTTPException(404, "Document not found") from None
    if path.parent != DATA_DIR.resolve() or path.suffix.lower() != ".pdf" or not path.is_file():
        raise HTTPException(404, "Document not found")
    return FileResponse(path, media_type="application/pdf")


@lru_cache
def feedback_store() -> FeedbackStore:
    return FeedbackStore(
        Path(os.getenv("FINSIGHT_FEEDBACK_DB", str(ROOT_DIR / "feedback.sqlite3"))),
        retention_days=int(os.getenv("FINSIGHT_FEEDBACK_RETENTION_DAYS", "30")),
    )


@app.post("/chat", response_model=ChatAnswer)
def chat(body: ChatRequest):
    answer = run(lambda: answer_chat(body), unavailable_message="The research assistant is unavailable. Check the transcript index and model configuration, then retry.")
    try:
        response_id, token = feedback_store().register(answer.model_dump(mode="json"), answer.model or ("pipeline:unreported-generator" if "generate" in answer.timings_ms else "pipeline:no-generation-recorded"))
        answer = answer.model_copy(update={"response_id": response_id, "feedback_token": token})
    except Exception as exc:
        # Review storage failure must never discard a successfully generated answer.
        log.error("Could not register answer for feedback: type=%s", type(exc).__name__)
    return answer


@app.post("/feedback", response_model=FeedbackReceipt)
def submit_feedback(body: FeedbackRequest):
    try:
        return feedback_store().submit(body)
    except FeedbackError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception as exc:
        log.error("Could not save answer feedback: type=%s", type(exc).__name__)
        raise HTTPException(503, "Feedback could not be saved. Your answer is still available; please retry.") from exc
