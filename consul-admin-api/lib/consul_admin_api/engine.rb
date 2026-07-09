module ConsulAdminApi
  class Engine < ::Rails::Engine
    initializer "consul_admin_api.middleware" do |app|
      app.middleware.insert_before(0, ConsulAdminApi::Middleware)
    end
  end
end
