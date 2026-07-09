# CONSUL harness

## Target software

- General CONSUL DEMOCRACY: `C:/Users/lukas/dev/consuldemocracy`
- Munich fork: `C:/Users/lukas/dev/consul-lhm-dev`

## Backend decision

CONSUL does not expose a complete operator/admin API. The harness therefore uses the
included `consul-admin-api` Rails middleware, which invokes the target installation's own
ActiveRecord models, validations, callbacks, translations, and lifecycle methods. The API
is enabled only when `CONSUL_ADMIN_API_TOKEN` is present.

The CLI detects Munich capabilities (`Projekt`, `ProjektPhase`, deficiency reports) at
runtime. Generic model commands preserve full coverage for optional modules and future
forks, while named resource groups provide predictable operator workflows.

## Coverage contract

- Instance and capability inspection
- Settings and municipal branding
- Users, verification, and operator roles
- Debates, proposals, comments, polls, budgets, legislation, pages, banners,
  newsletters, milestones, geozones, tags, and notifications
- Munich projects and project phases
- Generic model CRUD, lifecycle method calls, schema inspection, and JSON export
- Machine-readable `--json` output and an interactive default REPL

CONSUL does not provide transaction-level undo/redo for operator actions. The harness
therefore preserves model callbacks and audit records but does not claim reversible writes;
use database snapshots for destructive workflow rehearsals.
