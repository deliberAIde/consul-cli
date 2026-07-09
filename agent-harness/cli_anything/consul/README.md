# cli-anything-consul

`consul` gives an operator or AI agent complete access to a CONSUL DEMOCRACY
installation through its real Rails models. It supports upstream CONSUL and detects the
Munich fork's `Projekt` process layer automatically.

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
