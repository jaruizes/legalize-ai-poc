# ─── IAM ──────────────────────────────────────────────────────────────────────

resource "aws_iam_role" "lambda" {
  name = "${var.name_prefix}-api-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "${var.name_prefix}-api-lambda-bedrock"
  role = aws_iam_role.lambda.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockRetrieveAndGenerate"
        Effect = "Allow"
        Action = [
          "bedrock:RetrieveAndGenerate",
          "bedrock:Retrieve",
        ]
        Resource = "arn:aws:bedrock:${var.region}:${var.account_id}:knowledge-base/${var.knowledge_base_id}"
      },
      {
        Sid      = "BedrockInvokeModel"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = [
          # Inference profile
          "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.inference_profile_id}",
          # Cross-region inference profiles (e.g., eu.amazon.nova-lite-v1:0)
          "arn:aws:bedrock:*:${var.account_id}:inference-profile/${var.inference_profile_id}",
          # Foundation model (used internally by RetrieveAndGenerate)
          "arn:aws:bedrock:*::foundation-model/${var.generative_model_id}"
        ]
      },
      {
        Action   = "bedrock:GetInferenceProfile",
        Effect   = "Allow",
        Resource = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.inference_profile_id}",
        Sid      = "GetInferenceProfile"
      }
    ]
  })
}

# ─── Lambda ───────────────────────────────────────────────────────────────────

data "archive_file" "lambda" {
  type        = "zip"
  source_dir = "${path.root}/../../lambda"
  output_path = "${path.module}/lambda/handler.zip"
  excludes    = [
    "venv",
    "__pycache__",
    "*.pyc",
    "test_*.py",
    "test_*.json",
    "test.sh",
    "requirements.txt"
  ]
}

resource "aws_lambda_function" "ask" {
  function_name    = "${var.name_prefix}-api-ask"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  handler          = "handler.handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout
  role             = aws_iam_role.lambda.arn

  environment {
    variables = {
      KNOWLEDGE_BASE_ID     = var.knowledge_base_id
      INFERENCE_PROFILE_ARN = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.inference_profile_id}"
      SYSTEM_PROMPT         = var.system_prompt
      DEFAULT_TEMPERATURE   = tostring(var.default_temperature)
      DEFAULT_MAX_TOKENS    = tostring(var.default_max_tokens)
      DEFAULT_TOP_P         = tostring(var.default_top_p)
      DEFAULT_TOP_K         = tostring(var.default_top_k)
      DEFAULT_NUM_RESULTS   = tostring(var.default_num_results)
    }
  }
}

# ─── API Gateway ──────────────────────────────────────────────────────────────

resource "aws_api_gateway_rest_api" "this" {
  name        = "${var.name_prefix}-api"
  description = "Legalize AI PoC — query Spanish legislation via RAG"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "ask" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "ask"
}

resource "aws_api_gateway_method" "ask_post" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = aws_api_gateway_resource.ask.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "ask_post" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.ask.id
  http_method             = aws_api_gateway_method.ask_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ask.invoke_arn
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.ask.id,
      aws_api_gateway_method.ask_post.id,
      aws_api_gateway_integration.ask_post.id,
    ]))
  }

  depends_on = [aws_api_gateway_integration.ask_post]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name
}

# Allow API Gateway to invoke the Lambda
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ask.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}
