variable "name" {
  description = "Name for the OpenSearch Serverless collection"
  type        = string
}

variable "bedrock_iam_role_arn" {
  description = "ARN of the IAM role used by Bedrock"
  type        = string
}

variable "aws_caller_identity_arn" {
  description = "ARN of the AWS caller identity"
  type        = string
}

variable "vector_dimension" {
  description = "Dimension of the vector field"
  type        = number
  default     = 1024
}

variable "index_name" {
  description = "Name of the OpenSearch index"
  type        = string
  default     = "bedrock-knowledge-base-default-index"
}
