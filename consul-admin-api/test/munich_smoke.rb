require "json"

unless "Projekt".safe_constantize
  puts JSON.generate(status: "skipped", reason: "Munich Projekt model is not installed")
  exit 0
end

tracked_models = [
  Projekt,
  ProjektPhase,
  ProjektSetting,
  ProjektPhaseSetting,
  Proposal,
  SiteCustomization::Page,
  MapLocation
]
before = tracked_models.to_h { |model| [model.name, model.unscoped.count] }
result = {}

ActiveRecord::Base.transaction do
  executor = ConsulAdminApi::Executor.new
  project = executor.execute(
    "projekt.create",
    "name" => "CLI transactional smoke",
    "description" => "Rolled back after validation",
    "locale" => "de",
    "activate" => false
  )
  activated = executor.execute("projekt.activate", "id" => project.fetch("id"), "active" => true)
  phase = executor.execute(
    "projekt.add_phase",
    "id" => project.fetch("id"),
    "phase_type" => "proposal",
    "name" => "Transactional phase",
    "locale" => "de",
    "active" => true
  )
  recommendation = executor.execute(
    "projekt.publish_recommendation",
    "phase_id" => phase.fetch("id"),
    "title" => "Transactional recommendation",
    "description" => "This recommendation is rolled back after validation.",
    "tags" => ["smoke-test"],
    "locale" => "de"
  )

  raise "Project did not activate" unless activated.fetch("settings").fetch("projekt_feature.main.activate") == "active"
  raise "Unexpected phase type" unless phase.fetch("type") == "ProjektPhase::ProposalPhase"
  raise "Recommendation did not publish" if recommendation.fetch("published_at").nil?

  result = {
    project_id: project.fetch("id"),
    phase_id: phase.fetch("id"),
    recommendation_id: recommendation.fetch("id")
  }
  raise ActiveRecord::Rollback
end

after = tracked_models.to_h { |model| [model.name, model.unscoped.count] }
raise "Transactional smoke left records behind: #{before} -> #{after}" unless before == after

puts JSON.generate(status: "ok", rolled_back: true, result: result, counts: after)
