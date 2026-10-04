"""AI can explain an item and cannot change business records."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from tests.domain_app import DomainApp
from tests.integration.test_attention_engine import _owner
from tests.records import record_attention

from pulse_api.ai import ModelResult
from pulse_api.db import session_scope
from pulse_api.deps import get_language_model
from pulse_api.models import Action, AiRun, Customer


class ScriptedModel:
    name = "scripted"

    def complete(self, purpose: str, context: dict[str, object]) -> ModelResult:
        del context
        if purpose == "draft":
            payload: dict[str, object] = {
                "draft": "Thanks, I will reply tomorrow.",
                "tool": "delete",
            }
        else:
            payload = {"explanation": "A customer sent a short note.", "tool": "delete_all"}
        return ModelResult(payload, input_tokens=12, output_tokens=8)


def test_explain_does_not_follow_instructions_in_the_email(domain: DomainApp) -> None:
    _owner(domain)
    item_id = record_attention(domain, title="New email needs review")
    domain.client.app.dependency_overrides[get_language_model] = lambda: ScriptedModel()
    with session_scope(domain.factory) as session:
        session.add(
            Customer(
                tenant_id=_tenant_id(domain),
                name="Kept",
                email="kept@example.com",
            )
        )

    explained = domain.client.post(f"/attention/{item_id}/explain")
    assert explained.status_code == 200, explained.text
    assert explained.json() == {"text": "A customer sent a short note."}
    assert "tool" not in explained.text
    drafted = domain.client.post(f"/attention/{item_id}/draft")
    assert drafted.status_code == 200, drafted.text
    assert drafted.json()["text"] == "Thanks, I will reply tomorrow."

    with session_scope(domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 1
        assert session.scalar(select(func.count()).select_from(Action)) == 0
        runs = session.scalars(select(AiRun)).all()
        assert len(runs) == 2
        assert {run.purpose for run in runs} == {"explain", "draft"}
        assert all(run.status == "success" for run in runs)


def test_ai_budget_stops_another_call(domain: DomainApp, monkeypatch: pytest.MonkeyPatch) -> None:
    _owner(domain)
    item_id = record_attention(domain, title="New email needs review")
    domain.client.app.dependency_overrides[get_language_model] = lambda: ScriptedModel()
    monkeypatch.setenv("AI_DAILY_BUDGET", "1")
    from pulse_api.config import get_settings

    get_settings.cache_clear()
    first = domain.client.post(f"/attention/{item_id}/explain")
    second = domain.client.post(f"/attention/{item_id}/explain")
    assert first.status_code == 200, first.text
    assert second.status_code == 429


def test_unconfigured_ai_leaves_records_unchanged(domain: DomainApp) -> None:
    _owner(domain)
    item_id = record_attention(domain, title="New email needs review")
    denied = domain.client.post(f"/attention/{item_id}/explain")
    assert denied.status_code == 503
    with session_scope(domain.factory) as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 0
        failed = session.scalars(select(AiRun)).all()
        assert len(failed) == 1
        assert failed[0].status == "failed"
        assert failed[0].error_code == "unavailable"


def _tenant_id(domain: DomainApp) -> UUID:
    return UUID(domain.client.get("/me").json()["tenant"]["id"])
