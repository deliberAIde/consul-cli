from __future__ import annotations

import json
import mimetypes
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from ..core.config import Profile
from .consul_backend import ConsulBackendError


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class ConsulHTMLParser(HTMLParser):
    """Extract CSRF metadata and actionable HTML forms without browser automation."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.csrf_token: str | None = None
        self.forms: list[dict[str, Any]] = []
        self.flashes: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self._form: dict[str, Any] | None = None
        self._select: dict[str, Any] | None = None
        self._option: dict[str, Any] | None = None
        self._textarea: dict[str, Any] | None = None
        self._button: dict[str, Any] | None = None
        self._flash_depth = 0
        self._flash_parts: list[str] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = self._attrs(attrs)
        classes = set(values.get("class", "").split())
        flash_classes = {"alert", "notice", "success", "warning", "callout"}
        if self._flash_depth:
            self._flash_depth += int(tag not in VOID_ELEMENTS)
        elif classes & flash_classes:
            self._flash_depth = 1
            self._flash_parts = []

        if tag == "title":
            self._in_title = True
        elif tag == "meta" and values.get("name") == "csrf-token":
            self.csrf_token = values.get("content")
        elif tag == "form":
            self._form = {
                "action": values.get("action", ""),
                "method": values.get("method", "get").upper(),
                "id": values.get("id"),
                "class": values.get("class"),
                "fields": [],
            }
            self.forms.append(self._form)
        elif self._form is not None and tag == "input":
            name = values.get("name")
            if name:
                self._form["fields"].append(
                    {
                        "name": name,
                        "type": values.get("type", "text"),
                        "value": values.get("value", ""),
                        "required": "required" in values,
                        "checked": "checked" in values,
                        "disabled": "disabled" in values,
                    }
                )
        elif self._form is not None and tag == "select":
            name = values.get("name")
            if name:
                self._select = {
                    "name": name,
                    "type": "select",
                    "required": "required" in values,
                    "multiple": "multiple" in values,
                    "disabled": "disabled" in values,
                    "options": [],
                }
                self._form["fields"].append(self._select)
        elif self._select is not None and tag == "option":
            self._option = {
                "value": values.get("value", ""),
                "selected": "selected" in values,
                "text": "",
            }
            self._select["options"].append(self._option)
        elif self._form is not None and tag == "textarea":
            name = values.get("name")
            if name:
                self._textarea = {
                    "name": name,
                    "type": "textarea",
                    "required": "required" in values,
                    "disabled": "disabled" in values,
                    "value": "",
                }
                self._form["fields"].append(self._textarea)
        elif self._form is not None and tag == "button":
            self._button = {
                "name": values.get("name"),
                "type": values.get("type", "submit"),
                "value": values.get("value", ""),
                "disabled": "disabled" in values,
                "text": "",
            }
            self._form["fields"].append(self._button)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "form":
            self._form = None
            self._select = None
            self._option = None
            self._textarea = None
            self._button = None
        elif tag == "select":
            self._select = None
            self._option = None
        elif tag == "option":
            self._option = None
        elif tag == "textarea":
            self._textarea = None
        elif tag == "button":
            self._button = None

        if self._flash_depth and tag not in VOID_ELEMENTS:
            self._flash_depth -= 1
            if self._flash_depth == 0:
                text = " ".join(" ".join(self._flash_parts).split())
                if text and text not in self.flashes:
                    self.flashes.append(text)
                self._flash_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._flash_depth:
            self._flash_parts.append(data)
        if self._option is not None:
            self._option["text"] += data
        if self._textarea is not None:
            self._textarea["value"] += data
        if self._button is not None:
            self._button["text"] += data

    @property
    def title(self) -> str | None:
        title = " ".join("".join(self.title_parts).split())
        return title or None


def parse_html(text: str) -> dict[str, Any]:
    parser = ConsulHTMLParser()
    parser.feed(text)
    for form in parser.forms:
        method_override = next(
            (
                field["value"]
                for field in form["fields"]
                if field.get("name") == "_method" and field.get("value")
            ),
            None,
        )
        form["effective_method"] = (
            str(method_override).upper() if method_override else form["method"]
        )
        for field in form["fields"]:
            if "text" in field:
                field["text"] = " ".join(field["text"].split())
            if field.get("type") == "select":
                for option in field["options"]:
                    option["text"] = " ".join(option["text"].split())
    return {
        "title": parser.title,
        "csrf_token": parser.csrf_token,
        "forms": parser.forms,
        "flashes": parser.flashes,
    }


def flatten_form(values: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Convert nested JSON into the bracket notation expected by Rails forms."""

    result: list[tuple[str, str]] = []
    for key, value in values.items():
        field = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            result.extend(flatten_form(value, field))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    result.extend(flatten_form(item, f"{field}[{index}]"))
                else:
                    result.append((f"{field}[]", _form_value(item)))
        else:
            result.append((field, _form_value(value)))
    return result


def _form_value(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "1"
    if value is False:
        return "0"
    return str(value)


class ConsulWebBackend:
    """Authenticated controller-level adapter for every installed Rails route."""

    def __init__(self, profile: Profile, *, timeout: float | None = None):
        self.profile = profile
        self.base_url = profile.base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout if timeout is not None else profile.web_timeout,
            follow_redirects=True,
            verify=profile.verify_tls,
        )
        self._authenticated = False
        self._csrf_token: str | None = None

    def authenticate(
        self, login: str | None = None, password: str | None = None
    ) -> dict[str, Any]:
        login = login or self.profile.operator_login
        password = password or self.profile.resolved_operator_password
        if not login or not password:
            raise ConsulBackendError(
                "Operator credentials are missing; run profile set-operator or set "
                f"{self.profile.operator_password_env}"
            )

        response = self._authentication_request(
            "GET",
            self.profile.operator_login_path,
            action="load the operator login page",
        )
        self._raise_for_status(response, "load the operator login page")
        document = parse_html(response.text)
        form = self._login_form(document["forms"])
        defaults = {
            field["name"]: field.get("value", "")
            for field in form["fields"]
            if field.get("type") == "hidden"
        }
        login_field = self._field_name(form, ("[login]", "[email]", "login"))
        password_field = self._field_name(form, ("[password]", "password"))
        defaults[login_field] = login
        defaults[password_field] = password
        action = urljoin(str(response.url), form.get("action") or response.url.path)
        signed_in = self._authentication_request(
            "POST", action, action="sign in the operator", data=defaults
        )
        self._raise_for_status(signed_in, "sign in the operator")

        probe = self._authentication_request(
            "GET", self.profile.operator_probe_path, action="open the operator area"
        )
        self._raise_for_status(probe, "open the operator area")
        probe_document = parse_html(probe.text)
        if self.profile.operator_login_path in str(probe.url) or any(
            field.get("type") == "password"
            for form_item in probe_document["forms"]
            for field in form_item["fields"]
        ):
            raise ConsulBackendError("Operator login failed; credentials were rejected")

        self._authenticated = True
        self._csrf_token = probe_document["csrf_token"]
        return self._summary(probe, document=probe_document)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Path] | list[tuple[str, Path]] | None = None,
        json_body: bool = False,
        authenticate: bool = True,
        follow_redirects: bool = True,
        include_body: bool = False,
        include_forms: bool = False,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        if authenticate and not self._authenticated:
            self.authenticate()

        request_headers = {
            str(key): str(value) for key, value in (headers or {}).items()
        }
        if method in MUTATING_METHODS:
            if authenticate and not self._csrf_token:
                probe = self._authentication_request(
                    "GET",
                    self.profile.operator_probe_path,
                    action="refresh the operator CSRF token",
                )
                self._csrf_token = parse_html(probe.text)["csrf_token"]
            if self._csrf_token:
                request_headers.setdefault("X-CSRF-Token", self._csrf_token)
            request_headers.setdefault(
                "Referer", self.base_url + self.profile.operator_probe_path
            )

        values = params or {}
        handles = []
        try:
            request_files: list[tuple[str, tuple[str, Any, str]]] = []
            file_items = files.items() if isinstance(files, dict) else files or []
            for field, path_value in file_items:
                path_obj = Path(path_value)
                handle = path_obj.open("rb")
                handles.append(handle)
                content_type = (
                    mimetypes.guess_type(path_obj.name)[0] or "application/octet-stream"
                )
                request_files.append((field, (path_obj.name, handle, content_type)))

            kwargs: dict[str, Any] = {
                "headers": request_headers,
                "follow_redirects": follow_redirects,
            }
            if method in {"GET", "HEAD"}:
                kwargs["params"] = flatten_form(values)
            elif json_body:
                kwargs["json"] = values
            elif request_files:
                form_parts = [
                    (field, (None, value)) for field, value in flatten_form(values)
                ]
                kwargs["files"] = [*form_parts, *request_files]
            else:
                request_headers.setdefault(
                    "Content-Type", "application/x-www-form-urlencoded"
                )
                kwargs["content"] = urlencode(flatten_form(values))
            response = self._http.request(method, path, **kwargs)
        except (OSError, httpx.HTTPError) as exc:
            raise ConsulBackendError(f"CONSUL web request failed: {exc}") from exc
        finally:
            for handle in handles:
                handle.close()

        document = (
            parse_html(response.text)
            if "html" in response.headers.get("content-type", "")
            else None
        )
        if document and document.get("csrf_token"):
            self._csrf_token = document["csrf_token"]
        summary = self._summary(
            response,
            document=document,
            include_body=include_body,
            include_forms=include_forms,
        )
        if response.status_code >= 400:
            raise ConsulBackendError(
                f"CONSUL route returned HTTP {response.status_code}: "
                f"{summary.get('title') or response.text[:500]}"
            )
        if output_path is not None:
            destination = Path(output_path)
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(response.content)
            except OSError as exc:
                raise ConsulBackendError(
                    f"Could not write response to {destination}: {exc}"
                ) from exc
            summary["output"] = {
                "path": str(destination.resolve()),
                "bytes": len(response.content),
            }
        return summary

    def inspect(self, path: str, *, authenticate: bool = True) -> dict[str, Any]:
        return self.request("GET", path, authenticate=authenticate, include_forms=True)

    def _authentication_request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except (OSError, httpx.HTTPError) as exc:
            raise ConsulBackendError(f"Could not {action}: {exc}") from exc

    @staticmethod
    def _login_form(forms: list[dict[str, Any]]) -> dict[str, Any]:
        for form in forms:
            if any(field.get("type") == "password" for field in form["fields"]):
                return form
        raise ConsulBackendError("Operator login form was not found")

    @staticmethod
    def _field_name(form: dict[str, Any], suffixes: tuple[str, ...]) -> str:
        for field in form["fields"]:
            name = field.get("name", "")
            if any(name.endswith(suffix) for suffix in suffixes):
                return name
        raise ConsulBackendError(f"Login form is missing a field ending in {suffixes}")

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            raise ConsulBackendError(f"Could not {action}: HTTP {response.status_code}")

    @staticmethod
    def _summary(
        response: httpx.Response,
        *,
        document: dict[str, Any] | None = None,
        include_body: bool = False,
        include_forms: bool = False,
    ) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        result: dict[str, Any] = {
            "ok": response.status_code < 400,
            "status": response.status_code,
            "url": str(response.url),
            "content_type": content_type,
            "content_disposition": response.headers.get("content-disposition"),
            "redirects": [
                {
                    "status": item.status_code,
                    "url": str(item.url),
                    "location": item.headers.get("location"),
                }
                for item in response.history
            ],
        }
        if "json" in content_type:
            try:
                result["data"] = response.json()
            except json.JSONDecodeError:
                result["body"] = response.text
        elif document is not None:
            result["title"] = document["title"]
            result["flashes"] = document["flashes"]
            if include_forms:
                result["forms"] = document["forms"]
        if include_body:
            result["body"] = response.text
        return result
