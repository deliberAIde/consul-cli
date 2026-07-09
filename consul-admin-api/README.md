# consul-admin-api

Small Rails middleware used by `consul-cli`. It exposes a token-authenticated operator
endpoint backed by the installation's real ActiveRecord models and route set. It supports
Rails 5.2/Ruby 2.7 through Rails 8.0/Ruby 3.4 without adding JSON controllers to the host
application.

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

`execute` includes:

- model schema, CRUD, translations, attachments, and lifecycle calls;
- settings, users, roles, and high-level Munich project workflows;
- `route.list` for the installed Rails route manifest;
- `route.resolve` for named URL helpers and required path parameters;
- `route.audit` for an installation-derived operator coverage denominator.

Actual controller actions are sent by the CLI over a real authenticated web session. The
bridge does not reimplement controller orchestration or bypass controller authorization.
Rake tasks and Rails runner execute through the configured native application runtime.

The bridge grants installation-level operator access. Do not expose it without TLS,
network controls, and a secret unique to the installation.
