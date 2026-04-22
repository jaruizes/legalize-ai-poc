variable "name_prefix" {
  description = "Name prefix applied to all resources in this module"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base to query"
  type        = string
}

variable "generative_model_id" {
  description = "Bedrock foundation model ID or inference profile ARN/ID used for answer generation"
  type        = string
}

variable "inference_profile_id" {
  description = "Bedrock inference profile ID for Lambda IAM permissions"
  type        = string
}

variable "system_prompt" {
  description = "System prompt prepended to every request sent to the generative model"
  type        = string
  default     = "You are a Spanish legislation expert assistant. Answer questions accurately and concisely based on the provided legal documents. Respond in the same language as the question. Always cite the specific laws and articles you reference."
}

variable "stage_name" {
  description = "API Gateway deployment stage name"
  type        = string
  default     = "poc"
}

variable "lambda_runtime" {
  description = "Lambda runtime identifier"
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "default_temperature" {
  description = "Default inference temperature (0–1)"
  type        = number
  default     = 0.5
}

variable "default_max_tokens" {
  description = "Default maximum number of output tokens"
  type        = number
  default     = 512
}

variable "default_top_p" {
  description = "Default top-p nucleus sampling value (0–1)"
  type        = number
  default     = 0.9
}

variable "default_top_k" {
  description = "Default top-k sampling value"
  type        = number
  default     = 250
}

variable "default_num_results" {
  description = "Default number of knowledge base chunks to retrieve"
  type        = number
  default     = 5
}
