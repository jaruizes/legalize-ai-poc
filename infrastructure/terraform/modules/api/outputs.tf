output "api_endpoint" {
  description = "Invoke URL for the POST /ask endpoint"
  value       = "${aws_api_gateway_stage.this.invoke_url}/ask"
}

output "api_id" {
  description = "ID of the REST API"
  value       = aws_api_gateway_rest_api.this.id
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.ask.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.ask.arn
}

output "api_gateway_domain" {
  description = "API Gateway domain name without scheme (for CloudFront origin)"
  value       = "${aws_api_gateway_rest_api.this.id}.execute-api.${var.region}.amazonaws.com"
}

output "api_stage_path" {
  description = "API Gateway stage path used as CloudFront origin path (e.g. /poc)"
  value       = "/${var.stage_name}"
}
