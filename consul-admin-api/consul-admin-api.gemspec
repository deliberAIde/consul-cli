require_relative "lib/consul_admin_api/version"

Gem::Specification.new do |spec|
  spec.name = "consul-admin-api"
  spec.version = ConsulAdminApi::VERSION
  spec.authors = ["deliberAIde"]
  spec.summary = "Token-authenticated operator bridge for CONSUL DEMOCRACY"
  spec.description = "Exposes CONSUL's native models and route catalog without replacing domain logic."
  spec.homepage = "https://github.com/deliberAIde/consul-cli"
  spec.license = "AGPL-3.0-or-later"
  spec.required_ruby_version = ">= 2.7"
  spec.files = Dir["lib/**/*", "README.md"]
  spec.require_paths = ["lib"]
  spec.add_dependency "rails", ">= 5.2"
end
