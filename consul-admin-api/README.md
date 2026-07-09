# consul-admin-api

Small Rails middleware used by `consul-cli`. It exposes a token-authenticated operator
endpoint backed by the installation's real ActiveRecord models.

```ruby
# Gemfile_custom (or Gemfile)
gem "consul-admin-api", path: "/var/www/consul-admin-api"
```

For a source-mounted development checkout that should not alter `Gemfile.lock`, load the
bridge after `Bundler.require(*Rails.groups)` in `config/application.rb`:

```ruby
unless ENV["CONSUL_ADMIN_API_PATH"].to_s.empty?
  $LOAD_PATH.unshift(File.join(ENV.fetch("CONSUL_ADMIN_API_PATH"), "lib"))
  require "consul_admin_api"
end
```

Set `CONSUL_ADMIN_API_TOKEN` to a long random value and restart Rails. The endpoints are:

- `GET /consul_cli/v1/health`
- `POST /consul_cli/v1/execute`

The bridge grants installation-level operator access. Do not expose it without TLS,
network controls, and a secret unique to the installation.
