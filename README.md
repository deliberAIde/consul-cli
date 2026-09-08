# consul-cli

Full admin/operator CLI for
[CONSUL DEMOCRACY](https://github.com/consuldemocracy/consuldemocracy) and
compatible municipal forks, including Munich's `consul-lhm-dev`.

The CLI controls the target installation through four real application surfaces:

- authenticated Rails controller routes, including forms, CSRF, redirects, and files;
- ActiveRecord models, callbacks, translations, attachments, and lifecycle methods;
- every native Rake task exposed by the installed application;
- Rails runner for operator jobs and fork-specific code without a dedicated route or task.

This is comprehensive operator control-surface coverage, not a second implementation of
CONSUL's business logic. Authorization, validation, required parameters, and workflow
preconditions remain enforced by the installed application.

## Verified coverage

The same live E2E suite passes against both local targets:

| Target | Rails / Ruby | Operator routes | Controllers | Native tasks |
| --- | --- | ---: | ---: | ---: |
| Munich fork | 5.2.7.1 / 2.7.6 | 766 / 766 | 150 | 174 / 174 |
| Current upstream | 8.0.5 / 3.4.9 | 572 / 572 | 119 | 150 / 150 |

Machine-readable snapshots are in `coverage/`. Both report no unmapped route or Rake
task. Live tests authenticate through Devise, mutate a setting through the real admin
controller, verify persistence, establish CONSUL's separate management session, and
authorize all five non-admin operator roles. Temporary settings and roles are restored.

## Layout

- `agent-harness/`: installable CLI-Anything Python package and tests
- `consul-admin-api/`: token-authenticated Rails bridge for data and route discovery
- `coverage/`: per-installation operator coverage snapshots

See
[`agent-harness/cli_anything/consul/README.md`](agent-harness/cli_anything/consul/README.md)
for installation, profiles, and command examples.

## Install

```bash
pip install consul-democracy-cli      # commands: consul-democracy, consul
```

The package installs both `consul-democracy` and the shorter `consul`. If you also use
HashiCorp Consul, whose binary is called `consul` too, prefer `consul-democracy` or install
this CLI in its own virtual environment.

## Part of the civic tech agent-bridges toolkit

`consul-cli` is one bridge in the [civic tech agent-bridges toolkit](https://github.com/deliberAIde/civic-tech-agent-bridges): open-source
command-line clients that let any AI agent drive a civic-tech platform through its own API, so
platforms interoperate without waiting for a standards process. Sibling bridges: [polis-cli](https://github.com/deliberAIde/polis-cli) (Pol.is, Voxit), [decidim-cli](https://github.com/deliberAIde/decidim-cli) (Decidim), [deliberaide-cli](https://pypi.org/project/deliberaide-cli/) (deliberAIde).

## Relationship to upstream

This is an independent client. It contains no CONSUL DEMOCRACY source code and speaks only to the
documented HTTP surfaces of a running instance. deliberAIde offers it to the CONSUL DEMOCRACY community for
adoption; the Apache-2.0 licence is chosen so the code can be vendored into the AGPL-3.0 CONSUL
repositories without friction, since permissive code can be combined into copyleft ones but not
the other way round.

## Licence

Two licences, because this repository holds two kinds of code:

| Part | Licence | Why |
|---|---|---|
| `agent-harness/` (the CLI) | Apache-2.0 | Independent client; speaks HTTP to a running installation and contains no CONSUL source code |
| `consul-admin-api/` (the Rails engine) | AGPL-3.0-or-later | Loaded into and executed as part of the CONSUL application, which is AGPL-3.0 |

See [LICENSE](LICENSE), [NOTICE](NOTICE) and [`consul-admin-api/LICENSE`](consul-admin-api/LICENSE).
Copyright 2026 deliberAIde.
