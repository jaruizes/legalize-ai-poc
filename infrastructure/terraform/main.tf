module "s3_source_bucket" {
  source      = "./modules/s3_source"
  bucket_name = "${local.name_prefix}-data-${local.account_id}-${local.region_short}"
}

# Fetch the latest commit hash of the legislation repository to trigger sync on changes
data "external" "repo_commit" {
  program = ["sh", "-c", "echo \"{\\\"sha\\\": \\\"$(git ls-remote ${var.datasource_repo_url} HEAD | cut -f1)\\\"}\""]
}

resource "terraform_data" "sync_documents" {
  triggers_replace = [
    data.external.repo_commit.result.sha
  ]

  provisioner "local-exec" {
    command = <<-EOT
      TEMP_DIR=$(mktemp -d)
      git clone --depth 1 ${var.datasource_repo_url} $TEMP_DIR
      rm -rf $TEMP_DIR/.git
      aws s3 sync $TEMP_DIR s3://${module.s3_source_bucket.bucket_name}/ --delete --region ${local.region}
      rm -rf $TEMP_DIR
    EOT
  }

  depends_on = [module.s3_source_bucket]
}

module "vector_store" {
  source = "./modules/opensearch"

  name                    = local.name_prefix
  aws_caller_identity_arn = local.caller_identity_arn
  bedrock_iam_role_arn    = module.bedrock_kb.bedrock_iam_role_arn
  vector_dimension        = var.vector_dimension
}

module "bedrock_kb" {
  source = "./modules/bedrock_kb"

  account_id          = local.account_id
  name_prefix         = local.name_prefix
  collection_arn      = module.vector_store.collection_arn
  embedding_model_arn = local.bedrock_model_arn
  kb_name             = local.bedrock_kb_name
  region              = local.region
  s3_source_arn       = module.s3_source_bucket.bucket_arn
  storage_wait_id     = module.vector_store.sleep_id
  vector_index_name   = module.vector_store.index_name

  chunking_strategy                        = var.chunking_strategy
  fixed_size_max_tokens                    = var.fixed_size_max_tokens
  fixed_size_overlap_percentage            = var.fixed_size_overlap_percentage
  hierarchical_overlap_tokens              = var.hierarchical_overlap_tokens
  hierarchical_parent_max_tokens           = var.hierarchical_parent_max_tokens
  hierarchical_child_max_tokens            = var.hierarchical_child_max_tokens
  semantic_max_tokens                      = var.semantic_max_tokens
  semantic_buffer_size                     = var.semantic_buffer_size
  semantic_breakpoint_percentile_threshold = var.semantic_breakpoint_percentile_threshold
}

module "api" {
  source = "./modules/api"

  name_prefix          = local.name_prefix
  account_id           = local.account_id
  region               = local.region
  knowledge_base_id    = module.bedrock_kb.knowledge_base_id
  system_prompt        = var.api_system_prompt
  inference_profile_id = var.inference_profile_id
  generative_model_id  = var.generative_model_id
  default_max_tokens   = var.default_max_tokens

  guardrail_grounding_threshold = var.guardrail_grounding_threshold
  guardrail_relevance_threshold = var.guardrail_relevance_threshold
}

module "frontend" {
  source = "./modules/frontend"

  name_prefix = local.name_prefix
  bucket_name = "${local.name_prefix}-frontend-${local.account_id}-${local.region_short}"
  api_domain  = module.api.api_domain

  ui_title      = var.ui_title
  ui_subtitle   = var.ui_subtitle
  ui_icon       = var.ui_icon
  ui_examples   = var.ui_examples
  ui_disclaimer = var.ui_disclaimer
}
