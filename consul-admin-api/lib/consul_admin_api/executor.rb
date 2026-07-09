require "date"
require "base64"
require "stringio"

module ConsulAdminApi
  class Executor
    ROLE_MODELS = {
      "administrator" => "Administrator",
      "admin" => "Administrator",
      "moderator" => "Moderator",
      "manager" => "Manager",
      "valuator" => "Valuator",
      "poll_officer" => "Poll::Officer",
      "sdg_manager" => "SDG::Manager",
      "projekt_manager" => "ProjektManager"
    }.freeze

    PHASE_TYPES = {
      "comment" => "ProjektPhase::CommentPhase",
      "debate" => "ProjektPhase::DebatePhase",
      "proposal" => "ProjektPhase::ProposalPhase",
      "question" => "ProjektPhase::QuestionPhase",
      "voting" => "ProjektPhase::VotingPhase",
      "poll" => "ProjektPhase::VotingPhase",
      "budget" => "ProjektPhase::BudgetPhase",
      "legislation" => "ProjektPhase::LegislationPhase",
      "form" => "ProjektPhase::FormularPhase",
      "livestream" => "ProjektPhase::LivestreamPhase",
      "milestone" => "ProjektPhase::MilestonePhase",
      "notification" => "ProjektPhase::ProjektNotificationPhase",
      "event" => "ProjektPhase::EventPhase",
      "argument" => "ProjektPhase::ArgumentPhase",
      "newsfeed" => "ProjektPhase::NewsfeedPhase"
    }.freeze

    OPERATOR_ROUTE_NAMESPACES = %w[
      admin management moderation valuation officing sdg_management
    ].freeze

    ACTIONS = %w[
      instance.info instance.capabilities instance.models
      route.list route.resolve route.audit
      model.describe model.list model.get model.create model.update model.delete model.call
      settings.list settings.get settings.set settings.apply settings.reset_defaults
      user.create user.verify role.list role.assign role.remove
      attachment.list attachment.attach attachment.purge
      projekt.create projekt.activate projekt.set_setting projekt.add_phase projekt.publish_recommendation
      portal.brand_munich portal.bootstrap_munich portal.clean_participation
    ].freeze

    def execute(action, params = {})
      case action
      when "instance.info" then instance_info
      when "instance.capabilities" then capabilities
      when "instance.models" then models(params)
      when "route.list" then list_routes(params)
      when "route.resolve" then resolve_route(params)
      when "route.audit" then audit_routes(params)
      when "model.describe" then describe_model(params)
      when "model.list" then list_model(params)
      when "model.get" then get_model(params)
      when "model.create" then create_model(params)
      when "model.update" then update_model(params)
      when "model.delete" then delete_model(params)
      when "model.call" then call_model(params)
      when "settings.list" then list_settings(params)
      when "settings.get" then get_setting(params)
      when "settings.set" then set_setting(params)
      when "settings.apply" then apply_settings(params)
      when "settings.reset_defaults" then reset_settings
      when "user.create" then create_user(params)
      when "user.verify" then verify_user(params)
      when "role.list" then list_roles(params)
      when "role.assign" then assign_role(params)
      when "role.remove" then remove_role(params)
      when "attachment.list" then list_attachments(params)
      when "attachment.attach" then attach_file(params)
      when "attachment.purge" then purge_attachment(params)
      when "projekt.create" then create_projekt(params)
      when "projekt.activate" then activate_projekt(params)
      when "projekt.set_setting" then set_projekt_setting(params)
      when "projekt.add_phase" then add_projekt_phase(params)
      when "projekt.publish_recommendation" then publish_projekt_recommendation(params)
      when "portal.brand_munich" then brand_munich(params)
      when "portal.bootstrap_munich" then bootstrap_munich(params)
      when "portal.clean_participation" then clean_participation(params)
      else
        raise ArgumentError, "Unsupported CONSUL admin action: #{action}"
      end
    end

    def instance_info
      {
        bridge_version: ConsulAdminApi::VERSION,
        rails_version: Rails.version,
        ruby_version: RUBY_VERSION,
        environment: Rails.env,
        database: ActiveRecord::Base.connection.adapter_name,
        flavor: model_available?("Projekt") ? "munich" : "upstream",
        organization: setting_value("org_name"),
        public_url: setting_value("url")
      }
    end

    private

      def capabilities
        {
          actions: ACTIONS,
          core: {
            users: model_available?("User"),
            debates: model_available?("Debate"),
            proposals: model_available?("Proposal"),
            polls: model_available?("Poll"),
            budgets: model_available?("Budget"),
            legislation: model_available?("Legislation::Process"),
            pages: model_available?("SiteCustomization::Page"),
            newsletters: model_available?("Newsletter")
          },
          munich: {
            projekts: model_available?("Projekt"),
            projekt_phases: model_available?("ProjektPhase"),
            deficiency_reports: model_available?("DeficiencyReport"),
            formulars: model_available?("Formular")
          },
          full_model_access: true,
          lifecycle_method_calls: true
        }
      end

      def list_routes(params)
        scope = params.fetch("scope", "operator").to_s
        pattern = params["pattern"].to_s.downcase
        requested_verb = params["verb"].to_s.upcase
        requested_controller = params["controller"].to_s

        routes = Rails.application.routes.routes.filter_map do |route|
          controller = route.defaults[:controller].to_s
          action = route.defaults[:action].to_s
          next if controller.empty? || action.empty?
          next unless route_in_scope?(controller, scope)

          entry = serialize_route(route, controller, action)
          searchable = [
            entry[:name],
            entry[:controller],
            entry[:action],
            entry[:path],
            entry[:verbs].join(" ")
          ].compact.join(" ").downcase
          next if pattern.present? && !searchable.include?(pattern)
          next if requested_verb.present? && !entry[:verbs].include?(requested_verb)
          next if requested_controller.present? && entry[:controller] != requested_controller

          entry
        end

        routes.sort_by! do |route|
          [route[:controller], route[:action], route[:path], route[:verbs].join("|")]
        end
        {
          scope: scope,
          count: routes.length,
          namespaces: OPERATOR_ROUTE_NAMESPACES,
          routes: routes
        }
      end

      def resolve_route(params)
        name = params.fetch("name").to_s.sub(/_path\z/, "")
        route = Rails.application.routes.routes.find { |candidate| candidate.name.to_s == name }
        raise ArgumentError, "Unknown named Rails route: #{name}" unless route

        controller = route.defaults[:controller].to_s
        action = route.defaults[:action].to_s
        raise ArgumentError, "Route #{name} is not a controller route" if controller.empty? || action.empty?

        path_params = params["path_params"] || {}
        raise ArgumentError, "path_params must be an object" unless path_params.is_a?(Hash)
        helper = "#{name}_path"
        helpers = Rails.application.routes.url_helpers
        path = helpers.public_send(helper, path_params.symbolize_keys)
        serialize_route(route, controller, action).merge(path: path, helper: helper)
      rescue ActionController::UrlGenerationError => error
        raise ArgumentError, "Could not resolve #{name}: #{error.message}"
      end

      def audit_routes(params)
        manifest = list_routes(params.merge("scope" => params.fetch("scope", "operator")))
        routes = manifest[:routes]
        mutating = routes.select { |route| (route[:verbs] & %w[POST PUT PATCH DELETE]).any? }
        by_namespace = routes.group_by do |route|
          route[:controller].split("/", 2).first
        end.transform_values(&:length)
        {
          scope: manifest[:scope],
          total_routes: routes.length,
          mutating_routes: mutating.length,
          read_routes: routes.length - mutating.length,
          named_routes: routes.count { |route| route[:name].present? },
          unnamed_routes: routes.count { |route| route[:name].blank? },
          controllers: routes.map { |route| route[:controller] }.uniq.length,
          actions: routes.map { |route| [route[:controller], route[:action]] }.uniq.length,
          by_namespace: by_namespace.sort.to_h,
          addressable_routes: routes.length,
          uncovered_routes: [],
          coverage_basis: "Every listed route is addressable through authenticated web request by path; named routes are also resolvable by helper."
        }
      end

      def route_in_scope?(controller, scope)
        case scope
        when "all"
          true
        when "public"
          OPERATOR_ROUTE_NAMESPACES.none? { |namespace| controller.start_with?("#{namespace}/") }
        when "operator"
          OPERATOR_ROUTE_NAMESPACES.any? { |namespace| controller.start_with?("#{namespace}/") }
        when *OPERATOR_ROUTE_NAMESPACES
          controller.start_with?("#{scope}/")
        else
          raise ArgumentError, "Unknown route scope: #{scope}"
        end
      end

      def serialize_route(route, controller, action)
        {
          name: route.name&.to_s,
          verbs: normalize_route_verbs(route.verb),
          path: route.path.spec.to_s.sub(/\(\.:format\)\z/, ""),
          controller: controller,
          action: action,
          required_parts: Array(route.required_parts).map(&:to_s),
          defaults: route.defaults.each_with_object({}) do |(key, value), result|
            result[key.to_s] = serialize_value(value) if value.nil? || value.is_a?(String) ||
                                                     value.is_a?(Symbol) || value.is_a?(Numeric) ||
                                                     value == true || value == false
          end
        }
      end

      def normalize_route_verbs(verb)
        source = verb.respond_to?(:source) ? verb.source : verb.to_s
        source.scan(/\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/).uniq
      end

      def models(params)
        pattern = params["pattern"].to_s.downcase
        tables = ActiveRecord::Base.connection.tables.sort
        tables = tables.select { |name| name.downcase.include?(pattern) } unless pattern.empty?
        loaded_models = ActiveRecord::Base.descendants.map(&:name).compact.sort
        loaded_models = loaded_models.select { |name| name.downcase.include?(pattern) } unless pattern.empty?
        { tables: tables, loaded_models: loaded_models }
      end

      def describe_model(params)
        klass = model_class(params.fetch("model"))
        {
          model: klass.name,
          table: klass.table_name,
          columns: klass.columns.map do |column|
            {
              name: column.name,
              type: column.type,
              null: column.null,
              default: column.default
            }
          end,
          associations: klass.reflect_on_all_associations.map do |association|
            {
              name: association.name,
              macro: association.macro,
              class_name: association.class_name,
              foreign_key: association.foreign_key
            }
          end
        }
      end

      def list_model(params)
        klass = model_class(params.fetch("model"))
        relation = relation_for(klass, params["include_hidden"])
        where = params["where"] || {}
        raise ArgumentError, "where must be an object" unless where.is_a?(Hash)
        relation = relation.where(where) unless where.empty?
        relation = apply_order(relation, klass, params["order"])
        limit = [[params.fetch("limit", 100).to_i, 1].max, 1000].min
        offset = [params.fetch("offset", 0).to_i, 0].max
        fields = params["fields"]
        relation.limit(limit).offset(offset).map { |record| serialize_record(record, fields) }
      end

      def get_model(params)
        klass = model_class(params.fetch("model"))
        relation = relation_for(klass, params["include_hidden"])
        serialize_record(relation.find(params.fetch("id")))
      end

      def create_model(params)
        klass = model_class(params.fetch("model"))
        attributes = params.fetch("attributes")
        raise ArgumentError, "attributes must be an object" unless attributes.is_a?(Hash)

        record = nil
        in_locale(params["locale"]) do
          record = klass.new(attributes.except("translations"))
          record.save!
          apply_translations(record, attributes["translations"])
        end
        serialize_record(record)
      end

      def update_model(params)
        klass = model_class(params.fetch("model"))
        attributes = params.fetch("attributes")
        raise ArgumentError, "attributes must be an object" unless attributes.is_a?(Hash)

        record = relation_for(klass, true).find(params.fetch("id"))
        in_locale(params["locale"]) do
          record.update!(attributes.except("translations"))
          apply_translations(record, attributes["translations"])
        end
        serialize_record(record.reload)
      end

      def delete_model(params)
        klass = model_class(params.fetch("model"))
        record = relation_for(klass, true).find(params.fetch("id"))
        snapshot = serialize_record(record)
        params["hard"] ? record.delete : record.destroy!
        { deleted: true, hard: !!params["hard"], record: snapshot }
      end

      def call_model(params)
        klass = model_class(params.fetch("model"))
        receiver = params["id"] ? relation_for(klass, true).find(params["id"]) : klass
        method_name = params.fetch("method").to_s
        raise ArgumentError, "Private methods are not callable" if method_name.start_with?("_")
        args = params["args"] || []
        kwargs = (params["kwargs"] || {}).each_with_object({}) { |(key, value), result| result[key.to_sym] = value }
        raise ArgumentError, "args must be an array" unless args.is_a?(Array)
        raise ArgumentError, "kwargs must be an object" unless kwargs.is_a?(Hash)
        result = kwargs.empty? ? receiver.public_send(method_name, *args) : receiver.public_send(method_name, *args, **kwargs)
        serialize_value(result)
      end

      def list_settings(params)
        relation = Setting.order(:key)
        prefix = params["prefix"].to_s
        relation = relation.where("key LIKE ?", "#{prefix}%") unless prefix.empty?
        relation.map { |setting| { key: setting.key, value: setting.value } }
      end

      def get_setting(params)
        key = params.fetch("key")
        setting = Setting.find_by(key: key)
        { key: key, value: setting&.value, exists: !setting.nil? }
      end

      def set_setting(params)
        key = params.fetch("key")
        Setting[key] = params["value"]
        get_setting("key" => key)
      end

      def apply_settings(params)
        values = params.fetch("values")
        raise ArgumentError, "values must be an object" unless values.is_a?(Hash)
        ActiveRecord::Base.transaction do
          values.each { |key, value| Setting[key] = value }
        end
        values.keys.sort.map { |key| get_setting("key" => key) }
      end

      def reset_settings
        Setting.reset_defaults
        { reset: true, count: Setting.count }
      end

      def create_user(params)
        user = User.new(
          email: params.fetch("email"),
          username: params.fetch("username"),
          password: params.fetch("password"),
          password_confirmation: params.fetch("password")
        )
        user.confirmed_at = Time.current if params.fetch("confirmed", true) && user.respond_to?(:confirmed_at=)
        user.terms_of_service = "1" if user.respond_to?(:terms_of_service=)
        user.terms_data_storage = "1" if user.respond_to?(:terms_data_storage=)
        user.terms_data_protection = "1" if user.respond_to?(:terms_data_protection=)
        user.terms_general = "1" if user.respond_to?(:terms_general=)
        user.save!
        Administrator.find_or_create_by!(user_id: user.id) if params["admin"]
        serialize_record(user.reload).merge("roles" => roles_for(user))
      end

      def verify_user(params)
        user = User.unscoped.find(params.fetch("id"))
        level = params.fetch("level", 3).to_i
        now = Time.current
        attributes = { confirmed_at: user.confirmed_at || now }
        attributes[:level_two_verified_at] = now if level >= 2 && user.respond_to?(:level_two_verified_at=)
        attributes[:verified_at] = now if level >= 3 && user.respond_to?(:verified_at=)
        user.update!(attributes)
        serialize_record(user).merge("verification_level" => level)
      end

      def list_roles(params)
        users = if params["user_id"]
                  [User.unscoped.find(params["user_id"])]
                else
                  User.unscoped.order(:id).limit(1000)
                end
        users.map do |user|
          { user_id: user.id, email: user.email, username: user.username, roles: roles_for(user) }
        end
      end

      def assign_role(params)
        user = User.unscoped.find(params.fetch("user_id"))
        role = params.fetch("role").to_s.downcase
        if role.start_with?("official")
          level = role.split(":", 2)[1].to_i
          level = 1 if level < 1
          user.update!(official_level: [level, 5].min)
        else
          role_class = model_class(ROLE_MODELS.fetch(role) { raise ArgumentError, "Unknown role: #{role}" })
          role_class.find_or_create_by!(user_id: user.id)
        end
        { user_id: user.id, roles: roles_for(user.reload) }
      end

      def remove_role(params)
        user = User.unscoped.find(params.fetch("user_id"))
        role = params.fetch("role").to_s.downcase
        if role.start_with?("official")
          user.update!(official_level: 0)
        else
          role_class = model_class(ROLE_MODELS.fetch(role) { raise ArgumentError, "Unknown role: #{role}" })
          role_class.where(user_id: user.id).destroy_all
        end
        { user_id: user.id, roles: roles_for(user.reload) }
      end

      def create_projekt(params)
        projekt_class = model_class("Projekt")
        author_id = params["author_id"] || Administrator.first&.user_id || User.first&.id
        raise ArgumentError, "A project author is required" unless author_id
        projekt = nil
        ActiveRecord::Base.transaction do
          in_locale(params["locale"]) do
            projekt = projekt_class.create!(
              name: params.fetch("name"),
              description: params["description"].to_s,
              total_duration_start: params["start_date"].presence,
              total_duration_end: params["end_date"].presence,
              author_id: author_id,
              color: "#005A9C",
              order_number: 0
            )
          end
          projekt_class.ensure_order_integrity if projekt_class.respond_to?(:ensure_order_integrity)
          set_projekt_active(projekt, params["activate"])
        end
        serialize_projekt(projekt.reload)
      end

      def list_attachments(params)
        record = model_class(params.fetch("model")).unscoped.find(params.fetch("id"))
        names = if params["name"].present?
                  [params["name"]]
                elsif record.class.respond_to?(:attachment_reflections)
                  record.class.attachment_reflections.keys
                else
                  []
                end
        names.each_with_object({}) do |name, result|
          attachment = record.public_send(name)
          entries = attachment.respond_to?(:attachments) ? attachment.attachments : [attachment]
          result[name] = entries.select { |entry| entry.respond_to?(:attached?) && entry.attached? }.map do |entry|
            blob = entry.blob
            {
              attachment_id: entry.id,
              blob_id: blob.id,
              filename: blob.filename.to_s,
              content_type: blob.content_type,
              byte_size: blob.byte_size,
              checksum: blob.checksum
            }
          end
        end
      end

      def attach_file(params)
        record = model_class(params.fetch("model")).unscoped.find(params.fetch("id"))
        name = params.fetch("name").to_s
        attachment = record.public_send(name)
        bytes = Base64.strict_decode64(params.fetch("data"))
        attachment.attach(
          io: StringIO.new(bytes),
          filename: params.fetch("filename"),
          content_type: params["content_type"]
        )
        { attached: true, model: record.class.name, id: record.id, attachments: list_attachments(params) }
      end

      def purge_attachment(params)
        record = model_class(params.fetch("model")).unscoped.find(params.fetch("id"))
        name = params.fetch("name").to_s
        attachment = record.public_send(name)
        attachment.purge
        { purged: true, model: record.class.name, id: record.id, name: name }
      end

      def activate_projekt(params)
        projekt = model_class("Projekt").unscoped.find(params.fetch("id"))
        set_projekt_active(projekt, params.fetch("active", true))
        serialize_projekt(projekt.reload)
      end

      def set_projekt_setting(params)
        projekt = model_class("Projekt").unscoped.find(params.fetch("id"))
        setting = projekt.projekt_settings.find_or_initialize_by(key: params.fetch("key"))
        setting.update!(value: params["value"])
        { project_id: projekt.id, key: setting.key, value: setting.value }
      end

      def add_projekt_phase(params)
        projekt = model_class("Projekt").unscoped.find(params.fetch("id"))
        requested_type = params.fetch("phase_type").to_s
        class_name = PHASE_TYPES.fetch(requested_type.downcase, requested_type)
        phase_class = model_class(class_name)
        attributes = (params["attributes"] || {}).merge(
          "projekt_id" => projekt.id,
          "phase_tab_name" => params.fetch("name"),
          "start_date" => params["start_date"].presence,
          "end_date" => params["end_date"].presence,
          "active" => params.fetch("active", true),
          "given_order" => projekt.projekt_phases.maximum(:given_order).to_i + 1
        )
        phase = nil
        in_locale(params["locale"]) { phase = phase_class.create!(attributes) }
        serialize_record(phase.reload).merge("settings" => phase.settings.pluck(:key, :value).to_h)
      end

      def publish_projekt_recommendation(params)
        phase = model_class("ProjektPhase::ProposalPhase").unscoped.find(params.fetch("phase_id"))
        author_id = params["author_id"] || Administrator.first&.user_id || User.first&.id
        raise ArgumentError, "A recommendation author is required" unless author_id

        proposal = nil
        in_locale(params["locale"]) do
          proposal = model_class("Proposal").new(
            author_id: author_id,
            projekt_phase_id: phase.id,
            title: params.fetch("title"),
            description: params.fetch("description"),
            on_behalf_of: params["on_behalf_of"],
            resource_terms: "1"
          )
          proposal.tag_list = Array(params["tags"]).join(",") if params["tags"].present?
          proposal.save!
          proposal.publish
        end

        serialize_record(proposal.reload).merge(
          "project_id" => phase.projekt_id,
          "phase_id" => phase.id,
          "project_page_slug" => phase.projekt.page&.slug
        )
      end

      def brand_munich(params)
        values = {
          "url" => params.fetch("url", "http://127.0.0.1:3010"),
          "org_name" => "Landeshauptstadt M\u00FCnchen",
          "meta_title" => "unser.muenchen | Beteiligung der Landeshauptstadt M\u00FCnchen",
          "meta_description" => "Die Beteiligungsplattform der Landeshauptstadt M\u00FCnchen.",
          "proposal_code_prefix" => "MUC",
          "mailer_from_name" => "unser.muenchen",
          "map.latitude" => 48.1372,
          "map.longitude" => 11.5754,
          "map.zoom" => 11,
          "feature.facebook_login" => false,
          "feature.google_login" => false,
          "feature.twitter_login" => false,
          "feature.wordpress_login" => false,
          "extended_option.general.title" => "\u00D6ffentlichkeitsbeteiligung",
          "extended_option.general.subtitle" => "in M\u00FCnchen"
        }
        apply_settings("values" => values)
        { branded: true, organization: values["org_name"], url: values["url"], settings: values }
      end

      def bootstrap_munich(params)
        result = brand_munich(params)
        if model_available?("Projekt") && Projekt.respond_to?(:overview_page) && Projekt.overview_page.nil?
          author_id = Administrator.first&.user_id || User.first&.id
          overview = Projekt.create!(
            name: "Beteiligungsprojekte",
            special: true,
            special_name: "projekt_overview_page",
            author_id: author_id,
            color: "#005A9C"
          )
          result[:overview_project] = serialize_projekt(overview)
        end
        result.merge(capabilities: capabilities)
      end

      def clean_participation(params)
        models = %w[
          Comment Poll::Recount Poll::PartialResult Poll::Answer Poll::Question Poll
          Budget::Ballot Budget::Investment Budget
          Legislation::Proposal Legislation::Answer Legislation::Question Legislation::DraftVersion Legislation::Process
          Proposal Debate
        ]
        models << "Projekt" unless params["keep_projects"]
        removed = {}
        ActiveRecord::Base.transaction do
          models.each do |name|
            next unless model_available?(name)
            klass = model_class(name)
            removed[name] = klass.unscoped.count
            klass.unscoped.destroy_all
          end
        end
        { cleaned: true, removed: removed }
      end

      def set_projekt_active(projekt, active)
        setting = projekt.projekt_settings.find_or_initialize_by(key: "projekt_feature.main.activate")
        setting.update!(value: active ? "active" : "")
      end

      def serialize_projekt(projekt)
        serialize_record(projekt).merge(
          "page" => projekt.page ? serialize_record(projekt.page) : nil,
          "settings" => projekt.projekt_settings.pluck(:key, :value).to_h,
          "phase_ids" => projekt.projekt_phases.pluck(:id)
        )
      end

      def roles_for(user)
        roles = []
        ROLE_MODELS.values.uniq.each do |class_name|
          next unless model_available?(class_name)
          role_class = model_class(class_name)
          roles << ROLE_MODELS.key(class_name) if role_class.where(user_id: user.id).exists?
        end
        roles << "official:#{user.official_level}" if user.respond_to?(:official_level) && user.official_level.to_i > 0
        roles.compact
      end

      def model_class(name)
        klass = name.to_s.safe_constantize
        unless klass && klass.is_a?(Class) && klass < ActiveRecord::Base
          raise ArgumentError, "Unknown ActiveRecord model: #{name}"
        end
        klass
      end

      def model_available?(name)
        klass = name.to_s.safe_constantize
        klass && klass.is_a?(Class) && klass < ActiveRecord::Base && klass.table_exists?
      rescue StandardError
        false
      end

      def relation_for(klass, include_hidden)
        include_hidden ? klass.unscoped : klass.all
      end

      def apply_order(relation, klass, order)
        return relation if order.to_s.strip.empty?
        order.to_s.split(",").each do |clause|
          match = clause.strip.match(/\A([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(asc|desc))?\z/i)
          raise ArgumentError, "Invalid order clause: #{clause}" unless match
          field = match[1]
          raise ArgumentError, "Unknown order field #{field} for #{klass.name}" unless klass.column_names.include?(field)
          relation = relation.order(field => (match[2] || "asc").downcase.to_sym)
        end
        relation
      end

      def apply_translations(record, translations)
        return unless translations.is_a?(Hash)
        translations.each do |locale, values|
          raise ArgumentError, "translation values must be objects" unless values.is_a?(Hash)
          in_locale(locale) { record.update!(values) }
        end
      end

      def in_locale(locale)
        selected = (locale.presence || I18n.default_locale).to_sym
        if defined?(Globalize)
          Globalize.with_locale(selected) { yield }
        else
          I18n.with_locale(selected) { yield }
        end
      end

      def serialize_record(record, fields = nil)
        attributes = record.attributes
        if fields.is_a?(Array) && fields.any?
          unknown = fields - attributes.keys
          raise ArgumentError, "Unknown fields for #{record.class.name}: #{unknown.join(', ')}" if unknown.any?
          attributes = attributes.slice(*fields)
        end
        if record.respond_to?(:translations) && fields.nil?
          attributes = attributes.merge(
            "translations" => record.translations.map do |translation|
              translation.attributes.except("created_at", "updated_at")
            end
          )
        end
        serialize_value(attributes)
      rescue ActiveRecord::StatementInvalid
        serialize_value(attributes)
      end

      def serialize_value(value)
        case value
        when ActiveRecord::Relation
          value.limit(1000).map { |record| serialize_record(record) }
        when ActiveRecord::Base
          serialize_record(value)
        when Array
          value.map { |item| serialize_value(item) }
        when Hash
          value.each_with_object({}) { |(key, item), result| result[key] = serialize_value(item) }
        when Time, DateTime, Date
          value.iso8601
        when Symbol
          value.to_s
        when NilClass, String, Numeric, TrueClass, FalseClass
          value
        else
          value.respond_to?(:as_json) ? value.as_json : value.to_s
        end
      end

      def setting_value(key)
        return nil unless defined?(Setting) && Setting.table_exists?
        Setting[key]
      rescue StandardError
        nil
      end
  end
end
