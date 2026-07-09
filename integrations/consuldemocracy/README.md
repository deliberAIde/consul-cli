# Current upstream local integration

This override runs a sibling `consuldemocracy` checkout on port 3011 with the bridge
mounted read-only. The normal upstream Compose configuration remains unchanged.

Add this inert hook immediately after `Bundler.require(*Rails.groups)` in upstream
`config/application.rb`:

```ruby
unless ENV["CONSUL_ADMIN_API_PATH"].to_s.empty?
  $LOAD_PATH.unshift(File.join(ENV.fetch("CONSUL_ADMIN_API_PATH"), "lib"))
  require "consul_admin_api"
end
```

Create upstream's ignored local configuration:

```powershell
Copy-Item config/database.yml.example config/database.yml
Copy-Item config/secrets.yml.example config/secrets.yml
```

From the `consuldemocracy` checkout, with `consul-cli` as a sibling:

```powershell
$env:POSTGRES_PASSWORD = "..."
$env:CONSUL_ADMIN_API_TOKEN = "..."

docker compose `
  -f docker-compose.yml `
  -f ../consul-cli/integrations/consuldemocracy/docker-compose.cli.yml `
  up -d --build

docker compose `
  -f docker-compose.yml `
  -f ../consul-cli/integrations/consuldemocracy/docker-compose.cli.yml `
  run --rm --entrypoint /usr/local/bin/bundle app exec rails db:prepare
```

If database preparation as root creates unwritable local runtime files:

```powershell
docker compose `
  -f docker-compose.yml `
  -f ../consul-cli/integrations/consuldemocracy/docker-compose.cli.yml `
  run --rm --no-deps --user root --entrypoint /bin/chmod app -R a+rwX log tmp
```

The minimal seed creates `admin@consul.dev`. Configure the CLI profile with the app URL
`http://127.0.0.1:3011`, container `consuldemocracy-app-1`, and an operator password
environment variable. Do not commit `database.yml`, `secrets.yml`, database passwords,
bridge tokens, or operator passwords.
