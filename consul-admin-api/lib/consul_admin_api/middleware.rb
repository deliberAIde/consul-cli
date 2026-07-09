require "active_support/security_utils"
require "json"

module ConsulAdminApi
  class Middleware
    HEALTH_PATH = "/consul_cli/v1/health".freeze
    EXECUTE_PATH = "/consul_cli/v1/execute".freeze
    MAX_BODY_BYTES = 10 * 1024 * 1024

    def initialize(app)
      @app = app
    end

    def call(env)
      path = env["PATH_INFO"]
      return @app.call(env) unless path == HEALTH_PATH || path == EXECUTE_PATH

      token = ENV["CONSUL_ADMIN_API_TOKEN"].to_s
      return json_response(503, ok: false, error: "CONSUL admin API is disabled") if token.empty?
      return json_response(401, ok: false, error: "Unauthorized") unless authorized?(env, token)

      if path == HEALTH_PATH && env["REQUEST_METHOD"] == "GET"
        return json_response(200, ok: true, service: "consul-admin-api", data: Executor.new.instance_info)
      end

      return json_response(405, ok: false, error: "Method not allowed") unless env["REQUEST_METHOD"] == "POST"

      length = env["CONTENT_LENGTH"].to_i
      return json_response(413, ok: false, error: "Request body too large") if length > MAX_BODY_BYTES

      request = JSON.parse(env["rack.input"].read(MAX_BODY_BYTES + 1))
      data = Executor.new.execute(request.fetch("action"), request["params"] || {})
      json_response(200, ok: true, data: data)
    rescue JSON::ParserError => error
      json_response(400, ok: false, error_class: error.class.name, error: error.message)
    rescue KeyError, ArgumentError => error
      json_response(422, ok: false, error_class: error.class.name, error: error.message)
    rescue StandardError => error
      body = { ok: false, error_class: error.class.name, error: error.message }
      body[:backtrace] = error.backtrace.first(20) if ENV["CONSUL_ADMIN_API_DEBUG"] == "true"
      json_response(422, body)
    end

    private

      def authorized?(env, expected)
        supplied = env["HTTP_AUTHORIZATION"].to_s.sub(/\ABearer\s+/i, "")
        supplied.bytesize == expected.bytesize &&
          ActiveSupport::SecurityUtils.secure_compare(supplied, expected)
      end

      def json_response(status, body)
        payload = JSON.generate(body)
        [
          status,
          {
            "Content-Type" => "application/json; charset=utf-8",
            "Content-Length" => payload.bytesize.to_s,
            "Cache-Control" => "no-store"
          },
          [payload]
        ]
      end
  end
end
