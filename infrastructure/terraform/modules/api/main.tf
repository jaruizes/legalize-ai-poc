# ─── Locals ───────────────────────────────────────────────────────────────────

locals {
  # Derive region prefix (eu / us / ap) for cross-region inference profiles
  region_prefix = split("-", var.region)[0]
}

# ─── Bedrock Guardrail ────────────────────────────────────────────────────────
# Contextual grounding checks that the generated answer is:
#   · GROUNDING  — supported by the retrieved source chunks (reduces hallucination)
#   · RELEVANCE  — actually answers the user's question (reduces off-topic responses)
# Responses below the configured thresholds are blocked and replaced with a safe
# message, without exposing raw model output to the user.

resource "aws_bedrock_guardrail" "this" {
  name                      = "${var.name_prefix}-guardrail"
  blocked_input_messaging   = "Tu pregunta no parece estar relacionada con el contenido indexado. Por favor, formula una consulta sobre los documentos disponibles."
  blocked_outputs_messaging = "La respuesta generada no está suficientemente fundamentada en los documentos disponibles. Por favor, reformula la pregunta o amplía los filtros."

  contextual_grounding_policy_config {
    filters_config {
      type      = "GROUNDING"
      threshold = var.guardrail_grounding_threshold
    }
    filters_config {
      type      = "RELEVANCE"
      threshold = var.guardrail_relevance_threshold
    }
  }
}

resource "aws_bedrock_guardrail_version" "this" {
  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = "Managed by Terraform"
}

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

# ─── DynamoDB — interview sessions ────────────────────────────────────────────

resource "aws_dynamodb_table" "interviews" {
  name         = "${var.name_prefix}-interviews"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }
}

resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "${var.name_prefix}-api-lambda-dynamodb"
  role = aws_iam_role.lambda.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBInterviews"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
        ]
        Resource = aws_dynamodb_table.interviews.arn
      }
    ]
  })
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
        # Allow any inference profile owned by this account and any foundation model.
        # This lets the user switch models from the UI without requiring a policy update.
        Sid      = "BedrockInvokeModel"
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = [
          "arn:aws:bedrock:*:${var.account_id}:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      },
      {
        Sid      = "GetInferenceProfile"
        Effect   = "Allow"
        Action   = "bedrock:GetInferenceProfile"
        Resource = "arn:aws:bedrock:*:${var.account_id}:inference-profile/*"
      },
      {
        Sid      = "BedrockGuardrail"
        Effect   = "Allow"
        Action   = "bedrock:ApplyGuardrail"
        Resource = "arn:aws:bedrock:${var.region}:${var.account_id}:guardrail/${aws_bedrock_guardrail.this.guardrail_id}"
      }
    ]
  })
}

# ─── Lambda ───────────────────────────────────────────────────────────────────

data "archive_file" "lambda" {
  type        = "zip"
  source_dir = "${path.root}/../../lambda/ask"
  output_path = "${path.module}/lambda/ask/handler.zip"
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
      KNOWLEDGE_BASE_ID          = var.knowledge_base_id
      INFERENCE_PROFILE_ARN      = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${var.inference_profile_id}"
      INFERENCE_PROFILE_ARN_BASE = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/"
      FOUNDATION_MODEL_ARN_BASE  = "arn:aws:bedrock:${var.region}::foundation-model/"
      GUARDRAIL_ID               = aws_bedrock_guardrail.this.guardrail_id
      GUARDRAIL_VERSION          = aws_bedrock_guardrail_version.this.version
      SYSTEM_PROMPT              = var.system_prompt
      INTERVIEWS_TABLE           = aws_dynamodb_table.interviews.name
      SUMMARY_MODEL_ARN          = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${local.region_prefix}.amazon.nova-micro-v1:0"
      DEFAULT_TEMPERATURE   = tostring(var.default_temperature)
      DEFAULT_MAX_TOKENS    = tostring(var.default_max_tokens)
      DEFAULT_TOP_P         = tostring(var.default_top_p)
      DEFAULT_TOP_K         = tostring(var.default_top_k)
      DEFAULT_NUM_RESULTS   = tostring(var.default_num_results)
    }
  }
}

# ─── Lambda Function URL ──────────────────────────────────────────────────────
# Replaces API Gateway to remove the hard 29-second integration timeout.
# Lambda Function URLs support up to the full Lambda execution timeout (15 min),
# which allows long-running synthesis and report-generation queries to complete.

resource "aws_lambda_function_url" "ask" {
  function_name      = aws_lambda_function.ask.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["GET", "POST"]
    allow_headers     = ["content-type"]
    max_age           = 86400
  }
}
