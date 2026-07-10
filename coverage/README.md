# Operator coverage snapshots

These files are generated from running installations:

```powershell
consul --profile PROFILE coverage audit --scope operator --out coverage/FILE.json
```

| Snapshot | Operator routes | Controllers | Native Rake tasks |
| --- | ---: | ---: | ---: |
| `munich-operator-coverage.json` | 766/766 | 150 | 174/174 |
| `upstream-operator-coverage.json` | 572/572 | 119 | 150/150 |

Operator route scope includes `admin`, `management`, `moderation`, `valuation`,
`officing`, and `sdg_management`. The controller adapter establishes both the Devise
operator session and CONSUL's distinct management-console session.

`addressable_routes == total_routes` means every route discovered from
`Rails.application.routes` can be sent through the authenticated controller adapter.
Named routes can also be resolved through Rails URL helpers. Unnamed routes are invoked by
path.

`addressable_tasks == total_tasks` means every task returned by `rake -AT` can be
executed through the native runtime adapter with arguments and environment variables.
Rails runner covers application operations that are neither routes nor named Rake tasks.

These snapshots prove exhaustive execution-path coverage. They do not claim that every
destructive action was exercised with every possible state and parameter combination.
