# cli-anything-consul

`consul` gives an operator or AI agent comprehensive control of a CONSUL DEMOCRACY
installation through its real Rails controllers, models, Rake tasks, and Rails runtime.
It supports current upstream CONSUL and detects the Munich fork's `Projekt` process
layer automatically.

## Install

```powershell
cd agent-harness
python -m pip install -e ".[dev]"
```

Install and enable the sibling `consul-admin-api` gem in the target Rails app, set
`CONSUL_ADMIN_API_TOKEN`, then create a profile:

```powershell
consul profile add munich-local http://127.0.0.1:3010 `
  --token-env CONSUL_ADMIN_API_TOKEN `
  --app-path C:\Users\lukas\dev\consul-lhm-dev `
  --container consul-lhm-app-1 --default

consul instance health
consul --json instance info
consul instance capabilities
```

## Operator workflows

```powershell
consul settings brand-munich
consul users create operator@muenchen.de operator --admin
consul roles assign 2 moderator

consul projects create "Innenstadt 2030" `
  --description "Empfehlungen des Bürgerrats zur öffentlichen Diskussion" `
  --start-date 2026-09-17 --end-date 2026-10-31 --activate
consul projects add-phase 1 proposal --name "Empfehlungen kommentieren" `
  --start-date 2026-09-17 --end-date 2026-10-31
consul projects publish-recommendation 3 "Mehr Stadtgrün" `
  --body '@recommendation.md' --on-behalf-of "Bürgerrat München" `
  --tags "angenommen,stadtgruen"

consul proposals create --attrs '@proposal.json'
consul polls call publish --id 4
consul records describe 'Legislation::Process'
consul records list 'SiteCustomization::Page' --where '{"status":"published"}'
```

Every named resource group supports `list`, `get`, `create`, `update`, `delete`, and
`call`. `records` exposes the same operations for every installed ActiveRecord model,
which is the compatibility layer for optional modules and municipal forks.

Run `consul` without a subcommand for the persistent REPL. Add global `--json` before
the command for compact machine-readable output.

## Operator session

Controller-level commands use a real Devise login. Keep the password in an environment
variable:

```powershell
consul --profile munich-local profile set-operator admin@consul.dev `
  --password-env CONSUL_OPERATOR_PASSWORD
$env:CONSUL_OPERATOR_PASSWORD = "..."

consul --profile munich-local web login
consul --profile munich-local web inspect /admin/settings
```

The profile default is a 300-second web timeout for cold Rails development instances.
Set `--web-timeout` on `profile add` when a target needs a different value.

## Every controller route

```powershell
# Installed denominator and zero-gap audit
consul --profile munich-local routes audit --scope operator
consul --profile munich-local routes list --scope admin --controller admin/settings

# Resolve a named helper without sending a request
consul --profile munich-local routes resolve admin_setting `
  --path-params @setting-path.json

# Invoke the real controller action; mutating methods require confirmation or --yes
consul --profile munich-local web invoke admin_setting `
  --path-params @setting-path.json `
  --params @setting-update.json --yes

# Unnamed or fork-specific route
consul --profile munich-local web request PATCH /admin/custom_resource/42 `
  --params @payload.json --yes

# Multipart Rails form
consul --profile munich-local web request POST /admin/imports `
  --params @import.json --file "import[file]=C:\data\records.csv" --yes
```

`--params` accepts nested JSON and encodes Rails bracket notation. Repeat `--header`
and `--file` as needed. Use `--json-body` for JSON endpoints, `--include-forms` to
inspect returned forms, `--out report.pdf` to preserve a binary response, and
`--no-follow-redirects` when the redirect itself matters.

Operator scope includes the installed `admin`, `management`, `moderation`,
`valuation`, `officing`, and `sdg_management` namespaces. `--scope all` catalogs
the complete application.

## Native operations

```powershell
consul --profile munich-local runtime tasks
consul --profile munich-local runtime rake db:migrate --yes
consul --profile munich-local runtime rake projects:sync --arg 42 --yes
consul --profile munich-local runtime runner '@operator_job.rb' --yes
```

Runtime commands execute argument arrays directly, never through a shell. They can use a
configured Docker container or a local `--app-path`. Rake and runner execution require
confirmation unless `--yes` is supplied.

## Data and exports

Named resource groups are conveniences. `records` remains the universal installed-model
surface:

```powershell
consul records describe Setting
consul records list Setting --where @filters.json --limit 100
consul records call Proposal publish --id 42
consul export Proposal --out proposals.jsonl --format jsonl --include-hidden
```

Exports paginate until all matching rows are written; they are not capped at 1,000.

## Coverage audit

```powershell
consul --profile munich-local coverage audit --scope operator `
  --out coverage/munich-operator-coverage.json
```

The report combines the installed route catalog, native Rake catalog, bridge actions, and
named resources. `complete_control_surface_addressability` means every discovered route
and Rake task has an execution path. Each workflow still enforces its own authorization,
validations, required parameters, and state preconditions.

Verified snapshots:

- Munich Rails 5.2.7.1: 766/766 operator routes and 174/174 Rake tasks
- Upstream Rails 8.0.5: 572/572 operator routes and 150/150 Rake tasks

## Security

The bridge token and operator account both grant installation-level access. Use a unique
bridge token, TLS, network controls, and least-privilege operator accounts. Prefer
`--token-env` and `--password-env`; profile output always redacts stored secrets.
