from __future__ import annotations

import os

import pytest

from cli_anything.consul.core.config import Profile
from cli_anything.consul.utils.consul_backend import ConsulBackend


pytestmark = pytest.mark.skipif(
    os.environ.get("CONSUL_E2E") != "1",
    reason="Set CONSUL_E2E=1 to exercise the live local CONSUL bridge",
)


@pytest.fixture
def backend():
    token = os.environ.get("CONSUL_ADMIN_API_TOKEN")
    if not token:
        pytest.skip("Set CONSUL_ADMIN_API_TOKEN to exercise the live bridge")
    return ConsulBackend(
        Profile(
            name="e2e",
            base_url=os.environ.get("CONSUL_E2E_URL", "http://127.0.0.1:3010"),
            token=token,
        ),
        timeout=180,
    )


def test_live_operator_loop(backend):
    health = backend.health()
    assert health["ok"] is True

    info = backend.execute("instance.info")
    assert info["flavor"] in {"upstream", "munich"}

    capabilities = backend.execute("instance.capabilities")
    assert "model.list" in capabilities["actions"]

    previous_org = backend.execute("settings.get", key="org_name")["value"]
    try:
        backend.execute("settings.set", key="org_name", value="CLI E2E")
        assert backend.execute("settings.get", key="org_name")["value"] == "CLI E2E"
    finally:
        backend.execute("settings.set", key="org_name", value=previous_org)
