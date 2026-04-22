output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.knowledge_base.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.knowledge_base.arn
}

output "bedrock_iam_role_arn" {
  description = "ARN of the IAM role used by the Knowledge Base"
  value       = aws_iam_role.bedrock_kb_resource_kb.arn
}

output "bedrock_iam_role_name" {
  description = "Name of the IAM role used by the Knowledge Base"
  value       = aws_iam_role.bedrock_kb_resource_kb.name
}

output "data_source_id" {
  description = "ID of the Bedrock Knowledge Base Data Source"
  value       = aws_bedrockagent_data_source.this.data_source_id
}
