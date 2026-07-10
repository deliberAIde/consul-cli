from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest

from cli_anything.consul.core.config import Profile
from cli_anything.consul.utils.consul_backend import ConsulBackend
from cli_anything.consul.utils.runtime_backend import ConsulRuntimeBackend
from cli_anything.consul.utils.web_backend import ConsulWebBackend


pytestmark = pytest.mark.skipif(
    os.environ.get("CONSUL_E2E") != "1",
    reason="Set CONSUL_E2E=1 to exercise the live local CONSUL bridge",
)


@pytest.fixture
def profile():
    token = os.environ.get("CONSUL_ADMIN_API_TOKEN")
    if not token:
        pytest.skip("Set CONSUL_ADMIN_API_TOKEN to exercise the live bridge")
    return Profile(
        name="e2e",
        base_url=os.environ.get("CONSUL_E2E_URL", "http://127.0.0.1:3010"),
        token=token,
        operator_login=os.environ.get("CONSUL_E2E_LOGIN", "admin@consul.dev"),
        operator_password=os.environ.get("CONSUL_OPERATOR_PASSWORD"),
        container=os.environ.get("CONSUL_E2E_CONTAINER", "consul-lhm-app-1"),
    )


@pytest.fixture
def backend(profile):
    return ConsulBackend(profile, timeout=240)


def test_live_operator_loop(backend):
    health = backend.health()
    assert health["ok"] is True

    info = backend.execute("instance.info")
    assert info["flavor"] in {"upstream", "munich"}

    capabilities = backend.execute("instance.capabilities")
    assert "model.list" in capabilities["actions"]
    assert "route.audit" in capabilities["actions"]

    previous_org = backend.execute("settings.get", key="org_name")["value"]
    try:
        backend.execute("settings.set", key="org_name", value="CLI E2E")
        assert backend.execute("settings.get", key="org_name")["value"] == "CLI E2E"
    finally:
        backend.execute("settings.set", key="org_name", value=previous_org)


def test_live_operator_route_catalog_is_fully_addressable(backend):
    audit = backend.execute("route.audit", scope="operator")
    assert audit["total_routes"] > 0
    assert audit["mutating_routes"] > 0
    assert audit["controllers"] > 0
    assert audit["addressable_routes"] == audit["total_routes"]
    assert audit["uncovered_routes"] == []

    settings = backend.execute(
        "route.list",
        scope="admin",
        controller="admin/settings",
    )
    update = next(
        route for route in settings["routes"] if route["name"] == "admin_setting"
    )
    assert "PATCH" in update["verbs"]


def test_live_authenticated_controller_mutation_is_restored(profile, backend):
    if not profile.resolved_operator_password:
        pytest.skip("Set CONSUL_OPERATOR_PASSWORD to test real operator sessions")

    settings = backend.execute(
        "model.list",
        model="Setting",
        where={"key": "org_name"},
        order="id asc",
        limit=1,
        offset=0,
        include_hidden=True,
        fields=["id", "key", "value"],
    )
    assert len(settings) == 1
    setting = settings[0]
    route = backend.execute(
        "route.resolve",
        name="admin_setting",
        path_params={"id": setting["id"]},
    )
    assert route["path"].endswith(f"/admin/settings/{setting['id']}")

    web = ConsulWebBackend(profile, timeout=300)
    login = web.authenticate()
    assert login["status"] == 200
    assert login["url"].endswith("/admin")

    replacement = "CLI controller E2E"
    try:
        response = web.request(
            "PATCH",
            route["path"],
            params={"setting": {"value": replacement}},
            headers={"Referer": f"{profile.base_url}/admin/settings"},
        )
        assert response["status"] == 200
        assert any(item["status"] == 302 for item in response["redirects"])
        assert backend.execute("settings.get", key="org_name")["value"] == replacement
    finally:
        web.request(
            "PATCH",
            route["path"],
            params={"setting": {"value": setting["value"]}},
            headers={"Referer": f"{profile.base_url}/admin/settings"},
        )
        web._http.close()

    assert backend.execute("settings.get", key="org_name")["value"] == setting["value"]


def test_live_each_operator_role_namespace_is_authorized(profile, backend):
    if not profile.resolved_operator_password:
        pytest.skip("Set CONSUL_OPERATOR_PASSWORD to test real operator sessions")

    users = backend.execute(
        "model.list",
        model="User",
        where={"email": profile.operator_login},
        order="id asc",
        limit=1,
        offset=0,
        include_hidden=True,
        fields=["id", "email"],
    )
    assert len(users) == 1
    user_id = users[0]["id"]
    before = set(backend.execute("role.list", user_id=user_id)[0]["roles"])
    sdg_setting = backend.execute("settings.get", key="feature.sdg")
    sdg_before = sdg_setting["value"]

    namespaces = {
        "manager": "/management",
        "moderator": "/moderation",
        "valuator": "/valuation",
        "poll_officer": "/officing",
        "sdg_manager": "/sdg_management",
    }
    assigned: list[str] = []
    web: ConsulWebBackend | None = None

    try:
        for role in namespaces:
            if role not in before:
                backend.execute("role.assign", user_id=user_id, role=role)
                assigned.append(role)

        current = set(backend.execute("role.list", user_id=user_id)[0]["roles"])
        assert set(namespaces).issubset(current)

        backend.execute("settings.set", key="feature.sdg", value="true")

        web = ConsulWebBackend(profile, timeout=300)
        login = web.authenticate()
        assert urlparse(login["url"]).path == "/admin"

        for role, path in namespaces.items():
            response = web.request("GET", path)
            final_path = urlparse(response["url"]).path
            assert response["status"] == 200, role
            assert final_path.startswith(path), {
                "role": role,
                "requested": path,
                "final": final_path,
                "flashes": response.get("flashes"),
            }
    finally:
        if web is not None:
            web._http.close()
        try:
            for role in reversed(assigned):
                backend.execute("role.remove", user_id=user_id, role=role)
        finally:
            backend.execute("settings.set", key="feature.sdg", value=sdg_before)

    after = set(backend.execute("role.list", user_id=user_id)[0]["roles"])
    assert after == before
    assert backend.execute("settings.get", key="feature.sdg")["value"] == sdg_before


def test_live_native_runtime_surfaces(profile):
    if not profile.container and not profile.app_path:
        pytest.skip(
            "Set CONSUL_E2E_CONTAINER or app_path to test native runtime surfaces"
        )

    runtime = ConsulRuntimeBackend(profile, timeout=360)
    tasks = runtime.rake_tasks()
    assert tasks["count"] > 0
    assert any(task["name"] == "db:migrate" for task in tasks["tasks"])

    if os.environ.get("CONSUL_E2E_RUNNER") == "1":
        result = runtime.rails_runner("puts Rails.version", timeout=360)
        assert result["ok"] is True
        assert result["stdout"].strip()
