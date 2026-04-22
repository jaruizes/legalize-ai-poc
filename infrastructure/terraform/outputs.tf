output "s3_bucket_name" {
  description = "Name of the S3 source bucket"
  value       = module.s3_source_bucket.bucket_name
}

output "s3_bucket_arn" {
  description = "ARN of the S3 source bucket"
  value       = module.s3_source_bucket.bucket_arn
}

output "opensearch_collection_arn" {
  description = "ARN of the OpenSearch Serverless collection"
  value       = module.vector_store.collection_arn
}

output "opensearch_collection_endpoint" {
  description = "Endpoint of the OpenSearch Serverless collection"
  value       = module.vector_store.collection_endpoint
}

output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = module.bedrock_kb.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = module.bedrock_kb.knowledge_base_arn
}

output "data_source_id" {
  description = "ID of the Bedrock Knowledge Base Data Source"
  value       = module.bedrock_kb.data_source_id
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "api_endpoint" {
  description = "REST API endpoint URL for POST /ask"
  value       = module.api.api_endpoint
}

output "lambda_function_name" {
  description = "Name of the API Lambda function"
  value       = module.api.lambda_function_name
}

output "cloudfront_url" {
  description = "Public URL of the Consulta leyes app"
  value       = module.frontend.cloudfront_url
}

output "frontend_s3_bucket_name" {
  description = "S3 bucket that holds the built Angular app"
  value       = module.frontend.s3_bucket_name
}

output "frontend_cloudfront_distribution_id" {
  description = "CloudFront distribution ID (needed for cache invalidations)"
  value       = module.frontend.cloudfront_distribution_id
}
