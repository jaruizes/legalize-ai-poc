variable "kb_name" {
  description = "Name of the Knowledge Base"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix applied to all resources"
  type        = string
}

variable "embedding_model_arn" {
  description = "ARN of the embedding model"
  type        = string
}

variable "s3_source_arn" {
  description = "ARN of the S3 source bucket"
  type        = string
}

variable "collection_arn" {
  description = "ARN of the OpenSearch Serverless collection"
  type        = string
}

variable "account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "region" {
  description = "AWS Region"
  type        = string
}

variable "vector_index_name" {
  description = "Name of the vector index"
  type        = string
  default     = "bedrock-knowledge-base-default-index"
}

variable "vector_field" {
  description = "Name of the vector field"
  type        = string
  default     = "bedrock-knowledge-base-default-vector"
}

variable "chunking_strategy" {
  type        = string
  description = "Chunking strategy to use (DEFAULT, FIXED_SIZE, HIERARCHICAL, SEMANTIC)"
}

variable "fixed_size_max_tokens" {
  type        = number
  description = "Maximum number of tokens for fixed-size chunking"
}

variable "fixed_size_overlap_percentage" {
  type        = number
  description = "Percentage of overlap between chunks"
}

variable "hierarchical_overlap_tokens" {
  type        = number
  description = "Number of tokens to overlap in hierarchical chunking"
}

variable "hierarchical_parent_max_tokens" {
  type        = number
  description = "Maximum tokens for parent chunks"
}

variable "hierarchical_child_max_tokens" {
  type        = number
  description = "Maximum tokens for child chunks"
}

variable "semantic_max_tokens" {
  type        = number
  description = "Maximum tokens for semantic chunking"
}

variable "semantic_buffer_size" {
  type        = number
  description = "Buffer size for semantic chunking"
}

variable "semantic_breakpoint_percentile_threshold" {
  type        = number
  description = "Breakpoint percentile threshold for semantic chunking"
}

variable "storage_wait_id" {
  description = "ID to wait for before creating the Knowledge Base (e.g. from time_sleep)"
  type        = string
  default     = ""
}
