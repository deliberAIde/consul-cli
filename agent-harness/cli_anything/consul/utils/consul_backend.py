from __future__ import annotations

import json
from typing import Any

import httpx

from ..core.config import Profile


class ConsulBackendError(RuntimeError):
    pass


class ConsulBackend:
    """Token-authenticated adapter to the in-process CONSUL admin bridge."""

    def __init__(self, profile: Profile, *, timeout: float = 120.0):
        self.profile = profile
        self.base_url = profile.base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
            verify=profile.verify_tls,
        )

    def _headers(self) -> dict[str, str]:
        token = self.profile.resolved_token
        if not token:
            raise ConsulBackendError(
                f"Profile {self.profile.name!r} has no token; set {self.profile.token_env}"
            )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def health(self) -> dict[str, Any]:
        try:
            response = self._http.get("/consul_cli/v1/health", headers=self._headers())
        except httpx.HTTPError as exc:
            raise ConsulBackendError(
                f"CONSUL bridge is unreachable at {self.base_url}: {exc}"
            ) from exc
        return self._decode(response)

    def execute(self, action: str, **params: Any) -> Any:
        try:
            response = self._http.post(
                "/consul_cli/v1/execute",
                headers=self._headers(),
                json={"action": action, "params": params},
            )
        except httpx.HTTPError as exc:
            raise ConsulBackendError(f"CONSUL bridge request failed: {exc}") from exc
        payload = self._decode(response)
        if not payload.get("ok", False):
            error = payload.get("error", "unknown backend error")
            error_class = payload.get("error_class")
            prefix = f"{error_class}: " if error_class else ""
            raise ConsulBackendError(prefix + error)
        return payload.get("data")

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ConsulBackendError(
                f"CONSUL bridge returned HTTP {response.status_code} with non-JSON body: "
                f"{response.text[:500]}"
            ) from exc
        if response.status_code >= 400:
            raise ConsulBackendError(
                f"CONSUL bridge returned HTTP {response.status_code}: "
                f"{payload.get('error', payload)}"
            )
        return payload
