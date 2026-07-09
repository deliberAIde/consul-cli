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
controller, verify persistence, and restore the original value.

## Layout

- `agent-harness/`: installable CLI-Anything Python package and tests
- `consul-admin-api/`: token-authenticated Rails bridge for data and route discovery
- `coverage/`: per-installation operator coverage snapshots

See
[`agent-harness/cli_anything/consul/README.md`](agent-harness/cli_anything/consul/README.md)
for installation, profiles, and command examples.
