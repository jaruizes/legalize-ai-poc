variable "name_prefix" {
  description = "Name prefix applied to all resources"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for the frontend app"
  type        = string
}

variable "api_gateway_domain" {
  description = "API Gateway domain name without scheme (e.g. abc.execute-api.eu-west-1.amazonaws.com)"
  type        = string
}

variable "api_gateway_stage_path" {
  description = "API Gateway stage path used as CloudFront origin path (e.g. /poc)"
  type        = string
}
