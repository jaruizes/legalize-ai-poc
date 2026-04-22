output "collection_arn" {
  description = "ARN of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.resource_kb.arn
}

output "collection_endpoint" {
  description = "Endpoint of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.resource_kb.collection_endpoint
}

output "index_name" {
  description = "Name of the OpenSearch index"
  value       = opensearch_index.resource_kb.name
}

output "sleep_id" {
  description = "ID of the time_sleep resource to ensure proper ordering"
  value       = time_sleep.aws_iam_role_policy_bedrock_kb_resource_kb_oss.id
}
