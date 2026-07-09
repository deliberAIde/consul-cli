# consul-cli

Operator and agent CLI for [CONSUL DEMOCRACY](https://github.com/consuldemocracy/consuldemocracy)
and the Munich `consul-lhm-dev` fork.

The Python harness lives in `agent-harness/`. `consul-admin-api/` is a small,
token-authenticated Rails middleware gem that exposes CONSUL's real models and callbacks to
the CLI. It is intentionally separate from the CLI so it can be installed in upstream
CONSUL or a compatible municipal fork without duplicating domain logic.

See `agent-harness/cli_anything/consul/README.md` for installation and commands.
