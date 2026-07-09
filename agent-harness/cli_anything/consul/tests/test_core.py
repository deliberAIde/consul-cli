from __future__ import annotations

import json
import subprocess
from urllib.parse import parse_qs

import httpx
import pytest
from click.testing import CliRunner

from cli_anything.consul import consul_cli
from cli_anything.consul.core.config import (
    Profile,
    default_profile_name,
    list_profiles,
    load_profile,
    save_profile,
)
from cli_anything.consul.utils.consul_backend import ConsulBackendError
from cli_anything.consul.utils.runtime_backend import ConsulRuntimeBackend
from cli_anything.consul.utils.web_backend import (
    ConsulWebBackend,
    flatten_form,
    parse_html,
)


def test_profile_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSUL_CLI_HOME", str(tmp_path))
    monkeypatch.delenv("CONSUL_ADMIN_API_TOKEN", raising=False)
    monkeypatch.setenv("TEST_CONSUL_OPERATOR_PASSWORD", "operator-secret")
    save_profile(
        Profile(
            name="munich",
            base_url="http://127.0.0.1:3010",
            token="test-token",
            operator_login="admin@example.test",
            operator_password_env="TEST_CONSUL_OPERATOR_PASSWORD",
            container="consul-lhm-app-1",
        ),
        make_default=True,
    )

    assert default_profile_name() == "munich"
    assert list_profiles()["munich"]["container"] == "consul-lhm-app-1"
    assert load_profile().resolved_token == "test-token"
    assert load_profile().operator_login == "admin@example.test"
    assert load_profile().resolved_operator_password == "operator-secret"


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
    assert "routes" in result.output
    assert "web" in result.output
    assert "runtime" in result.output
    assert "coverage" in result.output


def test_html_form_parser_and_nested_rails_parameters():
    document = parse_html(
        """
        <html>
          <head><title>CONSUL Admin</title><meta name="csrf-token" content="csrf-1"></head>
          <body>
            <div class="alert success">Saved<br><strong>now</strong></div>
            <form action="/admin/settings/1" method="post">
              <input type="hidden" name="_method" value="patch">
              <input type="text" name="setting[value]" value="old" disabled>
              <select name="setting[kind]"><option value="a" selected> Alpha </option></select>
              <textarea name="setting[note]"> Public note </textarea>
              <button type="submit">Save setting</button>
            </form>
          </body>
        </html>
        """
    )
    form = document["forms"][0]
    assert document["title"] == "CONSUL Admin"
    assert document["csrf_token"] == "csrf-1"
    assert document["flashes"] == ["Saved now"]
    assert form["effective_method"] == "PATCH"
    assert form["fields"][1]["disabled"] is True
    assert form["fields"][2]["options"][0]["text"] == "Alpha"
    assert form["fields"][4]["text"] == "Save setting"

    assert flatten_form(
        {
            "proposal": {
                "title": "A",
                "published": True,
                "tags": ["green", "safe"],
                "translations": [{"locale": "de", "value": "Text"}],
            }
        }
    ) == [
        ("proposal[title]", "A"),
        ("proposal[published]", "1"),
        ("proposal[tags][]", "green"),
        ("proposal[tags][]", "safe"),
        ("proposal[translations][0][locale]", "de"),
        ("proposal[translations][0][value]", "Text"),
    ]


def test_web_backend_authenticates_and_sends_csrf(monkeypatch):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text=(
                    '<meta name="csrf-token" content="login-token">'
                    '<form action="/users/sign_in" method="post">'
                    '<input type="hidden" name="authenticity_token" value="login-token">'
                    '<input name="user[email]"><input type="password" name="user[password]">'
                    "</form>"
                ),
            )
        if request.method == "POST" and request.url.path == "/users/sign_in":
            seen["login"] = parse_qs(request.content.decode())
            return httpx.Response(200, text="<title>Signed in</title>")
        if request.method == "GET" and request.url.path == "/admin":
            return httpx.Response(
                200,
                text='<title>Admin</title><meta name="csrf-token" content="admin-token">',
            )
        if request.method == "PATCH" and request.url.path == "/admin/settings/1":
            seen["csrf"] = request.headers["X-CSRF-Token"]
            seen["referer"] = request.headers["Referer"]
            seen["params"] = parse_qs(request.content.decode())
            return httpx.Response(
                200,
                text='<title>Settings</title><div class="success">Saved</div>',
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    profile = Profile(
        name="test",
        base_url="http://consul.test",
        operator_login="admin@example.test",
        operator_password="secret",
    )
    backend = ConsulWebBackend(profile)
    backend._http.close()
    backend._http = httpx.Client(
        base_url=profile.base_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    login = backend.authenticate()
    response = backend.request(
        "PATCH",
        "/admin/settings/1",
        params={"setting": {"value": "CLI"}},
    )

    assert login["title"] == "Admin"
    assert seen["login"] == {
        "authenticity_token": ["login-token"],
        "user[email]": ["admin@example.test"],
        "user[password]": ["secret"],
    }
    assert seen["csrf"] == "admin-token"
    assert seen["referer"] == "http://consul.test/admin"
    assert seen["params"] == {"setting[value]": ["CLI"]}
    assert response["flashes"] == ["Saved"]


def test_web_backend_uses_profile_timeout_and_wraps_login_network_errors():
    profile = Profile(
        name="timeout",
        base_url="http://consul.test",
        operator_login="admin@example.test",
        operator_password="secret",
        web_timeout=17,
    )
    backend = ConsulWebBackend(profile)
    assert backend._http.timeout.read == 17
    backend._http.close()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("cold boot", request=request)

    backend._http = httpx.Client(
        base_url=profile.base_url,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ConsulBackendError, match="load the operator login page"):
        backend.authenticate()


def test_web_backend_sends_nested_fields_and_files_as_multipart(tmp_path):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["Content-Type"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            text="<title>Imported</title>",
            headers={"content-type": "text/html"},
        )

    profile = Profile(name="multipart", base_url="http://consul.test")
    backend = ConsulWebBackend(profile)
    backend._http.close()
    backend._http = httpx.Client(
        base_url=profile.base_url,
        transport=httpx.MockTransport(handler),
    )
    upload = tmp_path / "records.csv"
    upload.write_bytes(b"id,title\n1,Public square\n")
    second_upload = tmp_path / "more.csv"
    second_upload.write_bytes(b"id,title\n2,Library\n")
    file_values = (
        f"import[files][]={upload}",
        f"import[files][]={second_upload}",
    )
    files = consul_cli._file_pairs(file_values)
    assert files == [
        ("import[files][]", upload),
        ("import[files][]", second_upload),
    ]

    response = backend.request(
        "POST",
        "/admin/imports",
        params={"import": {"locale": "en"}},
        files=files,
        authenticate=False,
    )

    assert response["title"] == "Imported"
    assert str(seen["content_type"]).startswith("multipart/form-data; boundary=")
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b'name="import[locale]"' in body
    assert body.count(b'name="import[files][]"') == 2
    assert b'filename="records.csv"' in body
    assert b'filename="more.csv"' in body
    assert b"id,title\n1,Public square" in body
    assert b"id,title\n2,Library" in body


def test_web_backend_writes_binary_controller_response(tmp_path):
    content = b"%PDF-1.7\x00binary"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/report.pdf"
        return httpx.Response(
            200,
            content=content,
            headers={
                "content-type": "application/pdf",
                "content-disposition": 'attachment; filename="report.pdf"',
            },
        )

    profile = Profile(name="download", base_url="http://consul.test")
    backend = ConsulWebBackend(profile)
    backend._http.close()
    backend._http = httpx.Client(
        base_url=profile.base_url,
        transport=httpx.MockTransport(handler),
    )
    output = tmp_path / "reports" / "report.pdf"

    response = backend.request(
        "GET", "/admin/report.pdf", authenticate=False, output_path=output
    )

    assert output.read_bytes() == content
    assert response["content_disposition"] == 'attachment; filename="report.pdf"'
    assert response["output"]["bytes"] == len(content)
    assert response["output"]["path"] == str(output.resolve())


def test_runtime_backend_lists_and_invokes_native_tasks(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "rake db:migrate # Migrate the database\n"
                "rake projects:sync[id] # Sync one project\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = ConsulRuntimeBackend(
        Profile(
            name="test",
            base_url="http://consul.test",
            container="consul-app-1",
        )
    )

    tasks = backend.rake_tasks()
    assert tasks["count"] == 2
    assert tasks["tasks"][1]["name"] == "projects:sync"
    assert tasks["tasks"][1]["arguments"] == "id"

    backend.run_rake(
        "projects:sync",
        arguments=["1", "a,b"],
        env={"RAILS_ENV": "test"},
    )
    assert calls[-1] == [
        "docker",
        "exec",
        "-w",
        "/var/www/consul",
        "-e",
        "RAILS_ENV=test",
        "consul-app-1",
        "bundle",
        "exec",
        "rake",
        "projects:sync[1,a\\,b]",
    ]


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


def test_named_route_invocation_uses_resolved_controller_path(monkeypatch):
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeBridge:
        def execute(self, action, **params):
            assert action == "route.resolve"
            assert params == {
                "name": "admin_setting",
                "path_params": {"id": 4},
            }
            return {
                "name": "admin_setting",
                "verbs": ["PATCH", "PUT"],
                "path": "/admin/settings/4",
                "controller": "admin/settings",
                "action": "update",
            }

    class FakeWeb:
        def request(self, method, path, **params):
            calls.append((method, path, params))
            return {"ok": True, "status": 302}

    monkeypatch.setattr(consul_cli, "_backend", lambda runtime: FakeBridge())
    monkeypatch.setattr(consul_cli, "_web", lambda runtime: FakeWeb())
    result = CliRunner().invoke(
        consul_cli.cli,
        [
            "--json",
            "web",
            "invoke",
            "admin_setting",
            "--path-params",
            '{"id":4}',
            "--params",
            '{"setting":{"value":"CLI"}}',
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls[0][0:2] == ("PATCH", "/admin/settings/4")
    assert calls[0][2]["params"] == {"setting": {"value": "CLI"}}
    assert json.loads(result.output)["response"]["status"] == 302


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
