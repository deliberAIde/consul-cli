from __future__ import annotations

import json

from click.testing import CliRunner

from cli_anything.consul import consul_cli
from cli_anything.consul.core.config import (
    Profile,
    default_profile_name,
    list_profiles,
    load_profile,
    save_profile,
)


def test_profile_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSUL_CLI_HOME", str(tmp_path))
    monkeypatch.delenv("CONSUL_ADMIN_API_TOKEN", raising=False)
    save_profile(
        Profile(
            name="munich",
            base_url="http://127.0.0.1:3010",
            token="test-token",
            container="consul-lhm-app-1",
        ),
        make_default=True,
    )

    assert default_profile_name() == "munich"
    assert list_profiles()["munich"]["container"] == "consul-lhm-app-1"
    assert load_profile().resolved_token == "test-token"


def test_read_json_inline_and_file(tmp_path):
    assert consul_cli._read_json('{"status":"published"}') == {"status": "published"}
    path = tmp_path / "attrs.json"
    path.write_text('{"title":"Test"}', encoding="utf-8")
    assert consul_cli._read_json(f"@{path}") == {"title": "Test"}

    body = tmp_path / "body.md"
    body.write_text("Public recommendation", encoding="utf-8")
    assert consul_cli._read_text(f"@{body}") == "Public recommendation"


def test_help_exposes_named_and_generic_coverage():
    result = CliRunner().invoke(consul_cli.cli, ["--help"])
    assert result.exit_code == 0
    assert "records" in result.output
    assert "projects" in result.output
    assert "proposals" in result.output
    assert "legislation" in result.output


def test_json_command_output_is_machine_readable(monkeypatch):
    class FakeBackend:
        def execute(self, action, **params):
            assert action == "settings.get"
            assert params == {"key": "org_name"}
            return {"key": "org_name", "value": "Munich", "exists": True}

    monkeypatch.setattr(consul_cli, "_backend", lambda runtime: FakeBackend())
    result = CliRunner().invoke(
        consul_cli.cli, ["--json", "settings", "get", "org_name"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "key": "org_name",
        "value": "Munich",
        "exists": True,
    }


def test_named_resource_delegates_to_model_backend(monkeypatch):
    calls = []

    class FakeBackend:
        def execute(self, action, **params):
            calls.append((action, params))
            return {"id": 9}

    monkeypatch.setattr(consul_cli, "_backend", lambda runtime: FakeBackend())
    result = CliRunner().invoke(
        consul_cli.cli,
        ["--json", "proposals", "create", "--attrs", '{"author_id":1,"title":"A"}'],
    )
    assert result.exit_code == 0
    assert calls[0][0] == "model.create"
    assert calls[0][1]["model"] == "Proposal"


def test_publish_recommendation_uses_high_level_workflow(monkeypatch):
    calls = []

    class FakeBackend:
        def execute(self, action, **params):
            calls.append((action, params))
            return {"id": 12, "published_at": "2026-07-09T12:00:00Z"}

    monkeypatch.setattr(consul_cli, "_backend", lambda runtime: FakeBackend())
    result = CliRunner().invoke(
        consul_cli.cli,
        [
            "--json",
            "projects",
            "publish-recommendation",
            "7",
            "Mehr Stadtgruen",
            "--body",
            "Mit gesicherten Lieferzonen.",
            "--tags",
            "angenommen,begruenung",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "projekt.publish_recommendation",
            {
                "phase_id": "7",
                "title": "Mehr Stadtgruen",
                "description": "Mit gesicherten Lieferzonen.",
                "on_behalf_of": None,
                "tags": ["angenommen", "begruenung"],
                "author_id": None,
                "locale": "de",
            },
        )
    ]
