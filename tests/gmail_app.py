"""Gmail API harness. Identity override and the fake client exist only in tests."""

import base64
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from pulse_api.config import get_settings
from pulse_api.gmail.deps import get_gmail_client, get_oauth_state_store
from pulse_api.gmail.state_store import MemoryOAuthStateStore
from tests.domain_app import DomainApp
from tests.gmail_fakes import FakeGmailClient

TEST_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@dataclass
class GmailApp:
    domain: DomainApp
    store: MemoryOAuthStateStore
    fake: FakeGmailClient


@pytest.fixture
def gmail(domain: DomainApp, monkeypatch: pytest.MonkeyPatch) -> Iterator[GmailApp]:
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-client-secret-VALUE")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/integrations/gmail/callback")
    monkeypatch.setenv("WEB_APP_URL", "http://localhost:3000")
    get_settings.cache_clear()
    store = MemoryOAuthStateStore()
    fake = FakeGmailClient()
    app = domain.client.app
    app.dependency_overrides[get_oauth_state_store] = lambda: store
    app.dependency_overrides[get_gmail_client] = lambda: fake
    yield GmailApp(domain=domain, store=store, fake=fake)
    get_settings.cache_clear()
