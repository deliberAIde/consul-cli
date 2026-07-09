# Test plan

## Unit contracts

```powershell
python -m pytest -q cli_anything/consul/tests/test_core.py
python -m ruff check cli_anything/consul
python -m ruff format --check cli_anything/consul
```

The unit suite covers profile/secret behavior, CLI registration, nested Rails parameter
encoding, HTML form and method-override inspection, Devise/CSRF requests, clean timeout
errors, multipart files with byte preservation, route invocation, and shell-free Docker
runtime command construction.

## Live parity suite

Set these variables for the target:

```powershell
$env:CONSUL_E2E = "1"
$env:CONSUL_ADMIN_API_TOKEN = "..."
$env:CONSUL_OPERATOR_PASSWORD = "..."
$env:CONSUL_E2E_LOGIN = "admin@consul.dev"
$env:CONSUL_E2E_URL = "http://127.0.0.1:3010"
$env:CONSUL_E2E_CONTAINER = "consul-lhm-app-1"
$env:CONSUL_E2E_RUNNER = "1"

python -m pytest -q cli_anything/consul/tests/test_full_e2e.py
```

For current upstream, use URL `http://127.0.0.1:3011` and container
`consuldemocracy-app-1`.

Each live run verifies:

1. bridge health and flavor detection;
2. complete installed operator route addressability;
3. named admin route resolution;
4. real Devise login and CSRF;
5. a settings mutation through `Admin::SettingsController`;
6. persisted value verification and guaranteed restoration;
7. complete native Rake task discovery;
8. optional read-only Rails runner execution.

Verified results:

- Munich fork: 4 passed in 267.48 seconds
- Current upstream: 4 passed in 210.27 seconds
