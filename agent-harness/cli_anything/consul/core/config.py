from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def config_home() -> Path:
    return Path(os.environ.get("CONSUL_CLI_HOME", Path.home() / ".consul-cli"))


def config_path() -> Path:
    return config_home() / "config.json"


@dataclass(slots=True)
class Profile:
    name: str
    base_url: str
    token: str | None = None
    token_env: str = "CONSUL_ADMIN_API_TOKEN"
    app_path: str | None = None
    container: str | None = None
    container_workdir: str = "/var/www/consul"
    verify_tls: bool = True

    @property
    def resolved_token(self) -> str | None:
        return os.environ.get(self.token_env) or self.token


def _load() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {"default_profile": None, "profiles": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("default_profile", None)
    data.setdefault("profiles", {})
    return data


def _save(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def save_profile(profile: Profile, *, make_default: bool = False) -> None:
    data = _load()
    data["profiles"][profile.name] = asdict(profile)
    if make_default or not data.get("default_profile"):
        data["default_profile"] = profile.name
    _save(data)


def list_profiles() -> dict[str, dict[str, Any]]:
    return _load()["profiles"]


def default_profile_name() -> str | None:
    return _load().get("default_profile")


def set_default_profile(name: str) -> None:
    data = _load()
    if name not in data["profiles"]:
        raise KeyError(f"Unknown profile: {name}")
    data["default_profile"] = name
    _save(data)


def load_profile(name: str | None = None) -> Profile:
    data = _load()
    selected = name or data.get("default_profile")
    if not selected:
        raise KeyError("No CONSUL profile configured. Run: consul profile add ...")
    try:
        raw = data["profiles"][selected]
    except KeyError as exc:
        raise KeyError(f"Unknown profile: {selected}") from exc
    return Profile(**raw)


def remove_profile(name: str) -> None:
    data = _load()
    if name not in data["profiles"]:
        raise KeyError(f"Unknown profile: {name}")
    del data["profiles"][name]
    if data.get("default_profile") == name:
        data["default_profile"] = next(iter(data["profiles"]), None)
    _save(data)
