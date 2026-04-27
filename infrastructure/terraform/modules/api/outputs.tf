output "api_endpoint" {
  description = "Invoke URL for the POST /ask endpoint"
  value       = "${aws_lambda_function_url.ask.function_url}ask"
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.ask.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.ask.arn
}

output "api_domain" {
  description = "Lambda Function URL domain without scheme (for CloudFront origin)"
  # function_url is "https://<id>.lambda-url.<region>.on.aws/" — strip scheme and trailing slash
  value = trimsuffix(trimprefix(aws_lambda_function_url.ask.function_url, "https://"), "/")
}
