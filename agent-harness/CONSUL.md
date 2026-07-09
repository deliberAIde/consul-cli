# CONSUL harness

## Target software

- General CONSUL DEMOCRACY: `C:/Users/lukas/dev/consuldemocracy`
- Munich fork: `C:/Users/lukas/dev/consul-lhm-dev`

## Backend decision

CONSUL does not expose a complete operator/admin API. The harness therefore uses the
included `consul-admin-api` Rails middleware for token-authenticated model operations and
route discovery. Controller workflows themselves run over a real Devise operator session,
so CONSUL's authorization, strong parameters, services, callbacks, redirects, and views
remain authoritative.

There are four composable execution surfaces:

1. Named resource and workflow commands for common operations.
2. Generic ActiveRecord CRUD, attachments, translations, schema inspection, and public
   lifecycle calls for every installed model.
3. Generic authenticated HTTP execution for every mounted Rails controller route,
   including nested forms, CSRF, redirects, JSON, and multipart files.
4. Every native Rake task plus Rails runner for jobs and fork-specific operations outside
   the HTTP surface.

The CLI detects Munich capabilities (`Projekt`, `ProjektPhase`, deficiency reports) at
runtime. Fork-only models, routes, and Rake tasks do not require Python changes.

## Coverage contract

`routes audit --scope operator` obtains its denominator from the running installation.
Operator scope is the union of these namespaces:

- `admin`
- `management`
- `moderation`
- `valuation`
- `officing`
- `sdg_management`

A route is addressable when it can be sent by raw path; named routes can additionally be
resolved with Rails' own URL helper. A native task is addressable when it can be passed by
exact name and arguments to `bundle exec rake`. Rails runner is the final application-level
surface for non-route code.

Measured live snapshots:

| Installation | Routes | Mutating | Controllers | Rake tasks |
| --- | ---: | ---: | ---: | ---: |
| Munich fork | 766/766 | 402 | 150 | 174/174 |
| Upstream | 572/572 | 287 | 119 | 150/150 |

The parity E2E suite runs on Rails 5.2/Ruby 2.7 and Rails 8.0/Ruby 3.4. It verifies bridge
health, the route denominator, named helper resolution, Devise login, CSRF, a persisted
admin-controller mutation with restoration, task enumeration, and Rails runner.

## Limits

Comprehensive addressability does not mean every destructive workflow is executed during
tests. Individual actions still need valid parameters, authorization, and prerequisite
state. CONSUL has no transaction-level undo/redo for operator actions; use database
snapshots for destructive rehearsals. The CLI requires confirmation for generic mutating
HTTP, Rake, and runner commands.

The bridge is enabled only when `CONSUL_ADMIN_API_TOKEN` is present. Treat the token and
operator credentials as installation-level secrets.
