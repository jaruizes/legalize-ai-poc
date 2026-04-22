module "s3_source_bucket" {
  source      = "./modules/s3_source"
  bucket_name = "${local.name_prefix}-data-${local.account_id}-${local.region_short}"
}

resource "terraform_data" "sync_legalize_es" {
  triggers_replace = sha1(join(",", sort(fileset("${path.root}/../../legalize-es", "**/*.md"))))

  provisioner "local-exec" {
    command = "aws s3 sync ${path.root}/../../legalize-es s3://${module.s3_source_bucket.bucket_name}/ --delete --region ${local.region}"
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
}

module "frontend" {
  source = "./modules/frontend"

  name_prefix            = local.name_prefix
  bucket_name            = "${local.name_prefix}-frontend-${local.account_id}-${local.region_short}"
  api_gateway_domain     = module.api.api_gateway_domain
  api_gateway_stage_path = module.api.api_stage_path
}
