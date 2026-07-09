"""Full operator CLI for CONSUL DEMOCRACY and compatible forks."""

from __future__ import annotations

import json
import base64
import csv
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from click_repl import repl

from .core.config import (
    Profile,
    default_profile_name,
    list_profiles,
    load_profile,
    remove_profile,
    save_profile,
    set_default_profile,
)
from .core.resources import RESOURCE_MODELS
from .utils.consul_backend import ConsulBackend, ConsulBackendError


@dataclass(slots=True)
class Runtime:
    profile_name: str | None
    json_output: bool


def _read_json(value: str | None, *, expected: type | tuple[type, ...] = dict) -> Any:
    if value is None:
        return expected() if isinstance(expected, type) else {}
    if value.startswith("@"):
        text = Path(value[1:]).read_text(encoding="utf-8")
    else:
        path = Path(value)
        text = path.read_text(encoding="utf-8") if path.is_file() else value
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"Invalid JSON: {exc}") from exc
    if not isinstance(parsed, expected):
        names = (
            ", ".join(item.__name__ for item in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise click.BadParameter(f"JSON value must be {names}")
    return parsed


def _read_text(value: str) -> str:
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def _emit(runtime: Runtime, value: Any) -> None:
    if runtime.json_output:
        click.echo(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        )
    else:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _backend(runtime: Runtime) -> ConsulBackend:
    try:
        return ConsulBackend(load_profile(runtime.profile_name))
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


def _execute(runtime: Runtime, action: str, **params: Any) -> Any:
    try:
        data = _backend(runtime).execute(action, **params)
    except ConsulBackendError as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(runtime, data)
    return data


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option(
    "--profile", "profile_name", "-p", help="Configured CONSUL instance profile."
)
@click.option(
    "--json", "json_output", is_flag=True, help="Emit compact machine-readable JSON."
)
@click.pass_context
def cli(ctx: click.Context, profile_name: str | None, json_output: bool) -> None:
    """Operate a complete CONSUL installation from a shell or AI agent."""
    ctx.obj = Runtime(profile_name=profile_name, json_output=json_output)
    if ctx.invoked_subcommand is None:
        repl(ctx, prompt_kwargs={"message": "consul> "})


@cli.group("profile")
def profile_group() -> None:
    """Manage instance profiles."""


@profile_group.command("add")
@click.argument("name")
@click.argument("base_url")
@click.option(
    "--token", help="Bridge bearer token. Prefer --token-env outside local demos."
)
@click.option("--token-env", default="CONSUL_ADMIN_API_TOKEN", show_default=True)
@click.option("--app-path", type=click.Path(path_type=Path))
@click.option("--container")
@click.option("--container-workdir", default="/var/www/consul", show_default=True)
@click.option("--no-verify-tls", is_flag=True)
@click.option("--default", "make_default", is_flag=True)
@click.pass_obj
def profile_add(
    runtime: Runtime,
    name: str,
    base_url: str,
    token: str | None,
    token_env: str,
    app_path: Path | None,
    container: str | None,
    container_workdir: str,
    no_verify_tls: bool,
    make_default: bool,
) -> None:
    """Register a CONSUL instance."""
    profile = Profile(
        name=name,
        base_url=base_url,
        token=token,
        token_env=token_env,
        app_path=str(app_path.resolve()) if app_path else None,
        container=container,
        container_workdir=container_workdir,
        verify_tls=not no_verify_tls,
    )
    save_profile(profile, make_default=make_default)
    _emit(runtime, {"status": "saved", "profile": name, "base_url": base_url})


@profile_group.command("list")
@click.pass_obj
def profile_list(runtime: Runtime) -> None:
    profiles = list_profiles()
    default = default_profile_name()
    safe = {
        name: {
            **{key: value for key, value in entry.items() if key != "token"},
            "token_configured": bool(entry.get("token")),
            "default": name == default,
        }
        for name, entry in profiles.items()
    }
    _emit(runtime, safe)


@profile_group.command("show")
@click.argument("name", required=False)
@click.pass_obj
def profile_show(runtime: Runtime, name: str | None) -> None:
    try:
        profile = load_profile(name or runtime.profile_name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    value = (
        {key: val for key, val in profile.__dict__.items() if key != "token"}
        if hasattr(profile, "__dict__")
        else {
            "name": profile.name,
            "base_url": profile.base_url,
            "token_env": profile.token_env,
            "app_path": profile.app_path,
            "container": profile.container,
            "container_workdir": profile.container_workdir,
            "verify_tls": profile.verify_tls,
        }
    )
    value["token_configured"] = bool(profile.resolved_token)
    _emit(runtime, value)


@profile_group.command("default")
@click.argument("name")
@click.pass_obj
def profile_default(runtime: Runtime, name: str) -> None:
    try:
        set_default_profile(name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(runtime, {"status": "default", "profile": name})


@profile_group.command("remove")
@click.argument("name")
@click.confirmation_option(prompt="Remove this profile?")
@click.pass_obj
def profile_remove(runtime: Runtime, name: str) -> None:
    try:
        remove_profile(name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    _emit(runtime, {"status": "removed", "profile": name})


@cli.group("instance")
def instance_group() -> None:
    """Inspect the installation and bridge."""


@instance_group.command("health")
@click.pass_obj
def instance_health(runtime: Runtime) -> None:
    try:
        _emit(runtime, _backend(runtime).health())
    except ConsulBackendError as exc:
        raise click.ClickException(str(exc)) from exc


@instance_group.command("info")
@click.pass_obj
def instance_info(runtime: Runtime) -> None:
    _execute(runtime, "instance.info")


@instance_group.command("capabilities")
@click.pass_obj
def instance_capabilities(runtime: Runtime) -> None:
    _execute(runtime, "instance.capabilities")


@instance_group.command("models")
@click.option("--match", "pattern")
@click.pass_obj
def instance_models(runtime: Runtime, pattern: str | None) -> None:
    _execute(runtime, "instance.models", pattern=pattern)


@cli.group("settings")
def settings_group() -> None:
    """Read and update installation settings."""


@settings_group.command("list")
@click.option("--prefix")
@click.pass_obj
def settings_list(runtime: Runtime, prefix: str | None) -> None:
    _execute(runtime, "settings.list", prefix=prefix)


@settings_group.command("get")
@click.argument("key")
@click.pass_obj
def settings_get(runtime: Runtime, key: str) -> None:
    _execute(runtime, "settings.get", key=key)


@settings_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def settings_set(runtime: Runtime, key: str, value: str) -> None:
    _execute(runtime, "settings.set", key=key, value=value)


@settings_group.command("apply")
@click.argument("values")
@click.pass_obj
def settings_apply(runtime: Runtime, values: str) -> None:
    """Apply a JSON object (or @file) of setting keys and values."""
    _execute(runtime, "settings.apply", values=_read_json(values))


@settings_group.command("reset-defaults")
@click.confirmation_option(prompt="Reset all CONSUL settings to code defaults?")
@click.pass_obj
def settings_reset(runtime: Runtime) -> None:
    _execute(runtime, "settings.reset_defaults")


@settings_group.command("brand-munich")
@click.option("--url", default="http://127.0.0.1:3010", show_default=True)
@click.pass_obj
def settings_brand_munich(runtime: Runtime, url: str) -> None:
    _execute(runtime, "portal.brand_munich", url=url)


@cli.group("records")
def records_group() -> None:
    """Full-coverage ActiveRecord operations for installed modules."""


@records_group.command("describe")
@click.argument("model")
@click.pass_obj
def records_describe(runtime: Runtime, model: str) -> None:
    _execute(runtime, "model.describe", model=model)


def _list_model(
    runtime: Runtime,
    model: str,
    where: str | None,
    order: str | None,
    limit: int,
    offset: int,
    include_hidden: bool,
    fields: str | None,
) -> Any:
    return _execute(
        runtime,
        "model.list",
        model=model,
        where=_read_json(where),
        order=order,
        limit=limit,
        offset=offset,
        include_hidden=include_hidden,
        fields=[item.strip() for item in fields.split(",")] if fields else None,
    )


@records_group.command("list")
@click.argument("model")
@click.option("--where", help="JSON object or @file.")
@click.option("--order")
@click.option("--limit", default=100, type=click.IntRange(1, 1000), show_default=True)
@click.option("--offset", default=0, type=click.IntRange(min=0), show_default=True)
@click.option("--include-hidden", is_flag=True)
@click.option("--fields", help="Comma-separated fields.")
@click.pass_obj
def records_list(runtime: Runtime, model: str, **kwargs: Any) -> None:
    _list_model(runtime, model, **kwargs)


@records_group.command("get")
@click.argument("model")
@click.argument("record_id")
@click.option("--include-hidden", is_flag=True)
@click.pass_obj
def records_get(
    runtime: Runtime, model: str, record_id: str, include_hidden: bool
) -> None:
    _execute(
        runtime, "model.get", model=model, id=record_id, include_hidden=include_hidden
    )


@records_group.command("create")
@click.argument("model")
@click.option("--attrs", required=True, help="JSON object or @file.")
@click.option("--locale", default="de", show_default=True)
@click.pass_obj
def records_create(runtime: Runtime, model: str, attrs: str, locale: str) -> None:
    _execute(
        runtime,
        "model.create",
        model=model,
        attributes=_read_json(attrs),
        locale=locale,
    )


@records_group.command("update")
@click.argument("model")
@click.argument("record_id")
@click.option("--attrs", required=True, help="JSON object or @file.")
@click.option("--locale", default="de", show_default=True)
@click.pass_obj
def records_update(
    runtime: Runtime, model: str, record_id: str, attrs: str, locale: str
) -> None:
    _execute(
        runtime,
        "model.update",
        model=model,
        id=record_id,
        attributes=_read_json(attrs),
        locale=locale,
    )


@records_group.command("delete")
@click.argument("model")
@click.argument("record_id")
@click.option(
    "--hard",
    is_flag=True,
    help="Use delete! semantics and bypass soft-delete callbacks.",
)
@click.confirmation_option(prompt="Delete this record?")
@click.pass_obj
def records_delete(runtime: Runtime, model: str, record_id: str, hard: bool) -> None:
    _execute(runtime, "model.delete", model=model, id=record_id, hard=hard)


@records_group.command("call")
@click.argument("model")
@click.argument("method")
@click.option("--id", "record_id")
@click.option("--args", default="[]", help="JSON array or @file.")
@click.option("--kwargs", default="{}", help="JSON object or @file.")
@click.pass_obj
def records_call(
    runtime: Runtime,
    model: str,
    method: str,
    record_id: str | None,
    args: str,
    kwargs: str,
) -> None:
    _execute(
        runtime,
        "model.call",
        model=model,
        id=record_id,
        method=method,
        args=_read_json(args, expected=list),
        kwargs=_read_json(kwargs),
    )


def _make_resource_group(name: str, model: str) -> click.Group:
    @click.group(
        name=name, help=f"Operate {model} records with native model callbacks."
    )
    def group() -> None:
        pass

    @group.command("list")
    @click.option("--where")
    @click.option("--order")
    @click.option(
        "--limit", default=100, type=click.IntRange(1, 1000), show_default=True
    )
    @click.option("--offset", default=0, type=click.IntRange(min=0), show_default=True)
    @click.option("--include-hidden", is_flag=True)
    @click.option("--fields")
    @click.pass_obj
    def list_command(runtime: Runtime, **kwargs: Any) -> None:
        _list_model(runtime, model, **kwargs)

    @group.command("get")
    @click.argument("record_id")
    @click.option("--include-hidden", is_flag=True)
    @click.pass_obj
    def get_command(runtime: Runtime, record_id: str, include_hidden: bool) -> None:
        _execute(
            runtime,
            "model.get",
            model=model,
            id=record_id,
            include_hidden=include_hidden,
        )

    @group.command("create")
    @click.option("--attrs", required=True)
    @click.option("--locale", default="de", show_default=True)
    @click.pass_obj
    def create_command(runtime: Runtime, attrs: str, locale: str) -> None:
        _execute(
            runtime,
            "model.create",
            model=model,
            attributes=_read_json(attrs),
            locale=locale,
        )

    @group.command("update")
    @click.argument("record_id")
    @click.option("--attrs", required=True)
    @click.option("--locale", default="de", show_default=True)
    @click.pass_obj
    def update_command(
        runtime: Runtime, record_id: str, attrs: str, locale: str
    ) -> None:
        _execute(
            runtime,
            "model.update",
            model=model,
            id=record_id,
            attributes=_read_json(attrs),
            locale=locale,
        )

    @group.command("delete")
    @click.argument("record_id")
    @click.option("--hard", is_flag=True)
    @click.confirmation_option(prompt=f"Delete this {model} record?")
    @click.pass_obj
    def delete_command(runtime: Runtime, record_id: str, hard: bool) -> None:
        _execute(runtime, "model.delete", model=model, id=record_id, hard=hard)

    @group.command("call")
    @click.argument("method")
    @click.option("--id", "record_id")
    @click.option("--args", default="[]")
    @click.option("--kwargs", default="{}")
    @click.pass_obj
    def call_command(
        runtime: Runtime,
        method: str,
        record_id: str | None,
        args: str,
        kwargs: str,
    ) -> None:
        _execute(
            runtime,
            "model.call",
            model=model,
            id=record_id,
            method=method,
            args=_read_json(args, expected=list),
            kwargs=_read_json(kwargs),
        )

    return group


for resource_name, resource_model in RESOURCE_MODELS.items():
    cli.add_command(_make_resource_group(resource_name, resource_model))


@cli.group("users")
def users_group() -> None:
    """Manage users and verification."""


@users_group.command("list")
@click.option("--where")
@click.option("--limit", default=100, type=click.IntRange(1, 1000))
@click.pass_obj
def users_list(runtime: Runtime, where: str | None, limit: int) -> None:
    _list_model(runtime, "User", where, "id asc", limit, 0, True, None)


@users_group.command("create")
@click.argument("email")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--admin", is_flag=True)
@click.option("--confirmed/--unconfirmed", default=True)
@click.pass_obj
def users_create(
    runtime: Runtime,
    email: str,
    username: str,
    password: str,
    admin: bool,
    confirmed: bool,
) -> None:
    _execute(
        runtime,
        "user.create",
        email=email,
        username=username,
        password=password,
        admin=admin,
        confirmed=confirmed,
    )


@users_group.command("verify")
@click.argument("user_id")
@click.option("--level", default=3, type=click.IntRange(1, 3), show_default=True)
@click.pass_obj
def users_verify(runtime: Runtime, user_id: str, level: int) -> None:
    _execute(runtime, "user.verify", id=user_id, level=level)


@cli.group("roles")
def roles_group() -> None:
    """Assign and remove operator roles."""


@roles_group.command("list")
@click.argument("user_id", required=False)
@click.pass_obj
def roles_list(runtime: Runtime, user_id: str | None) -> None:
    _execute(runtime, "role.list", user_id=user_id)


@roles_group.command("assign")
@click.argument("user_id")
@click.argument("role")
@click.pass_obj
def roles_assign(runtime: Runtime, user_id: str, role: str) -> None:
    _execute(runtime, "role.assign", user_id=user_id, role=role)


@roles_group.command("remove")
@click.argument("user_id")
@click.argument("role")
@click.confirmation_option(prompt="Remove this role?")
@click.pass_obj
def roles_remove(runtime: Runtime, user_id: str, role: str) -> None:
    _execute(runtime, "role.remove", user_id=user_id, role=role)


@cli.group("projects")
def projects_group() -> None:
    """Manage Munich Projekt process wrappers when available."""


@cli.group("attachments")
def attachments_group() -> None:
    """Upload, inspect, and purge Active Storage attachments."""


@attachments_group.command("list")
@click.argument("model")
@click.argument("record_id")
@click.option("--name", help="Attachment association name, such as image or documents.")
@click.pass_obj
def attachments_list(
    runtime: Runtime, model: str, record_id: str, name: str | None
) -> None:
    _execute(runtime, "attachment.list", model=model, id=record_id, name=name)


@attachments_group.command("upload")
@click.argument("model")
@click.argument("record_id")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", required=True, help="Attachment association name.")
@click.option("--content-type")
@click.pass_obj
def attachments_upload(
    runtime: Runtime,
    model: str,
    record_id: str,
    path: Path,
    name: str,
    content_type: str | None,
) -> None:
    guessed_type = (
        content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    )
    _execute(
        runtime,
        "attachment.attach",
        model=model,
        id=record_id,
        name=name,
        filename=path.name,
        content_type=guessed_type,
        data=base64.b64encode(path.read_bytes()).decode("ascii"),
    )


@attachments_group.command("purge")
@click.argument("model")
@click.argument("record_id")
@click.argument("name")
@click.confirmation_option(prompt="Purge this attachment?")
@click.pass_obj
def attachments_purge(runtime: Runtime, model: str, record_id: str, name: str) -> None:
    _execute(runtime, "attachment.purge", model=model, id=record_id, name=name)


@projects_group.command("list")
@click.option("--include-hidden", is_flag=True)
@click.pass_obj
def projects_list(runtime: Runtime, include_hidden: bool) -> None:
    _execute(
        runtime,
        "model.list",
        model="Projekt",
        where={},
        order="order_number asc",
        limit=1000,
        offset=0,
        include_hidden=include_hidden,
        fields=None,
    )


@projects_group.command("create")
@click.argument("name")
@click.option("--description", default="")
@click.option("--start-date")
@click.option("--end-date")
@click.option("--author-id")
@click.option("--locale", default="de", show_default=True)
@click.option("--activate/--draft", default=False)
@click.pass_obj
def projects_create(
    runtime: Runtime,
    name: str,
    description: str,
    start_date: str | None,
    end_date: str | None,
    author_id: str | None,
    locale: str,
    activate: bool,
) -> None:
    _execute(
        runtime,
        "projekt.create",
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
        author_id=author_id,
        locale=locale,
        activate=activate,
    )


@projects_group.command("activate")
@click.argument("project_id")
@click.pass_obj
def projects_activate(runtime: Runtime, project_id: str) -> None:
    _execute(runtime, "projekt.activate", id=project_id, active=True)


@projects_group.command("deactivate")
@click.argument("project_id")
@click.pass_obj
def projects_deactivate(runtime: Runtime, project_id: str) -> None:
    _execute(runtime, "projekt.activate", id=project_id, active=False)


@projects_group.command("set")
@click.argument("project_id")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def projects_set(runtime: Runtime, project_id: str, key: str, value: str) -> None:
    _execute(runtime, "projekt.set_setting", id=project_id, key=key, value=value)


@projects_group.command("add-phase")
@click.argument("project_id")
@click.argument("phase_type")
@click.option("--name", required=True)
@click.option("--start-date")
@click.option("--end-date")
@click.option("--active/--inactive", default=True)
@click.option("--attrs", default="{}")
@click.option("--locale", default="de", show_default=True)
@click.pass_obj
def projects_add_phase(
    runtime: Runtime,
    project_id: str,
    phase_type: str,
    name: str,
    start_date: str | None,
    end_date: str | None,
    active: bool,
    attrs: str,
    locale: str,
) -> None:
    _execute(
        runtime,
        "projekt.add_phase",
        id=project_id,
        phase_type=phase_type,
        name=name,
        start_date=start_date,
        end_date=end_date,
        active=active,
        attributes=_read_json(attrs),
        locale=locale,
    )


@projects_group.command("publish-recommendation")
@click.argument("phase_id")
@click.argument("title")
@click.option("--body", required=True, help="Public description text or @file.")
@click.option("--on-behalf-of")
@click.option("--tags", help="Comma-separated public tags.")
@click.option("--author-id")
@click.option("--locale", default="de", show_default=True)
@click.pass_obj
def projects_publish_recommendation(
    runtime: Runtime,
    phase_id: str,
    title: str,
    body: str,
    on_behalf_of: str | None,
    tags: str | None,
    author_id: str | None,
    locale: str,
) -> None:
    _execute(
        runtime,
        "projekt.publish_recommendation",
        phase_id=phase_id,
        title=title,
        description=_read_text(body),
        on_behalf_of=on_behalf_of,
        tags=[item.strip() for item in tags.split(",") if item.strip()] if tags else [],
        author_id=author_id,
        locale=locale,
    )


@cli.group("portal")
def portal_group() -> None:
    """Bootstrap, clean, and prepare an installation."""


@portal_group.command("clean-participation")
@click.option("--keep-projects", is_flag=True)
@click.confirmation_option(prompt="Delete participation content from this instance?")
@click.pass_obj
def portal_clean(runtime: Runtime, keep_projects: bool) -> None:
    _execute(runtime, "portal.clean_participation", keep_projects=keep_projects)


@portal_group.command("bootstrap-munich")
@click.option("--url", default="http://127.0.0.1:3010", show_default=True)
@click.pass_obj
def portal_bootstrap_munich(runtime: Runtime, url: str) -> None:
    _execute(runtime, "portal.bootstrap_munich", url=url)


@cli.command("export")
@click.argument("model")
@click.option("--where")
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "jsonl", "csv"]),
    default="json",
    show_default=True,
)
@click.option("--include-hidden", is_flag=True)
@click.pass_obj
def export_model(
    runtime: Runtime,
    model: str,
    where: str | None,
    out: Path,
    output_format: str,
    include_hidden: bool,
) -> None:
    data = _backend(runtime).execute(
        "model.list",
        model=model,
        where=_read_json(where),
        order="id asc",
        limit=1000,
        offset=0,
        include_hidden=include_hidden,
        fields=None,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        out.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    elif output_format == "jsonl":
        lines = [json.dumps(record, ensure_ascii=False, default=str) for record in data]
        out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        fieldnames = sorted({key for record in data for key in record})
        with out.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in data:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False, default=str)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in record.items()
                    }
                )
    _emit(
        runtime,
        {
            "status": "written",
            "format": output_format,
            "path": str(out.resolve()),
            "records": len(data),
        },
    )


def main() -> None:
    cli(prog_name="consul")


if __name__ == "__main__":
    main()
