data "aws_partition" "current" {}

resource "aws_iam_role" "bedrock_kb_resource_kb" {
  name = "AmazonBedrockExecutionRoleForKnowledgeBase_${var.kb_name}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${var.account_id}:knowledge-base/*"
          }
        }
      }
    ]
  })
}

# Knowledge base bedrock invoke policy
resource "aws_iam_role_policy" "bedrock_kb_resource_kb_model" {
  name = "AmazonBedrockFoundationModelPolicyForKnowledgeBase_${var.kb_name}"
  role = aws_iam_role.bedrock_kb_resource_kb.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "bedrock:InvokeModel"
        Effect   = "Allow"
        Resource = "${var.embedding_model_arn}"
      }
    ]
  })
}

# Knowledge base S3 policy
resource "aws_iam_role_policy" "bedrock_kb_resource_kb_s3" {
  name = "AmazonBedrockS3PolicyForKnowledgeBase_${var.kb_name}"
  role = aws_iam_role.bedrock_kb_resource_kb.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ListBucketStatement"
        Action   = "s3:ListBucket"
        Effect   = "Allow"
        Resource = var.s3_source_arn
        Condition = {
          StringEquals = {
            "aws:ResourceAccount" = var.account_id
          }
      } },
      {
        Sid      = "S3GetObjectStatement"
        Action   = "s3:GetObject"
        Effect   = "Allow"
        Resource = "${var.s3_source_arn}/*"
        Condition = {
          StringEquals = {
            "aws:ResourceAccount" = var.account_id
          }
        }
      }
    ]
  })
}

# Knowledge base opensearch access policy
resource "aws_iam_role_policy" "bedrock_kb_resource_kb_oss" {
  name = "AmazonBedrockOSSPolicyForKnowledgeBase_${var.kb_name}"
  role = aws_iam_role.bedrock_kb_resource_kb.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "aoss:APIAccessAll"
        Effect   = "Allow"
        Resource = var.collection_arn
      }
    ]
  })
}

# Intermediate S3 bucket for Bedrock custom transformation
resource "aws_s3_bucket" "intermediate" {
  bucket        = "${var.name_prefix}-bedrock-temp-${var.account_id}"
  force_destroy = true
}

# IAM Role for Enrichment Lambda
resource "aws_iam_role" "enricher_lambda" {
  name = "${var.name_prefix}-enricher-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "enricher_lambda_basic" {
  role       = aws_iam_role.enricher_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Grant the enricher Lambda read/write access to the intermediate temp bucket
resource "aws_iam_role_policy" "enricher_lambda_s3" {
  name = "${var.name_prefix}-enricher-s3-policy"
  role = aws_iam_role.enricher_lambda.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TempBucketReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource = "${aws_s3_bucket.intermediate.arn}/*"
      },
      {
        Sid      = "TempBucketList"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.intermediate.arn
      }
    ]
  })
}

# Zip the Lambda code
data "archive_file" "enricher_zip" {
  type        = "zip"
  source_file = "${path.root}/../../lambda/enricher/handler.py"
  output_path = "${path.root}/../../lambda/enricher.zip"
}

# Enrichment Lambda Function
resource "aws_lambda_function" "enricher" {
  filename         = data.archive_file.enricher_zip.output_path
  function_name    = "${var.name_prefix}-enricher"
  role             = aws_iam_role.enricher_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.enricher_zip.output_base64sha256
  timeout          = 60
}

# Allow Bedrock to invoke the Lambda
resource "aws_lambda_permission" "allow_bedrock" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.enricher.function_name
  principal     = "bedrock.amazonaws.com"
  # Removing source_arn temporarily to ensure connectivity
}

# Update Bedrock KB Role to allow Lambda invocation and S3 access
resource "aws_iam_role_policy" "bedrock_kb_custom_transformation" {
  name = "AmazonBedrockCustomTransformationPolicy_${var.kb_name}"
  role = aws_iam_role.bedrock_kb_resource_kb.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "lambda:InvokeFunction"
        Effect   = "Allow"
        Resource = [
          aws_lambda_function.enricher.arn,
          "${aws_lambda_function.enricher.arn}:*"
        ]
      },
      {
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Effect   = "Allow"
        Resource = [
          aws_s3_bucket.intermediate.arn,
          "${aws_s3_bucket.intermediate.arn}/*"
        ]
      }
    ]
  })
}

# Knowledge base resource creation
resource "aws_bedrockagent_knowledge_base" "knowledge_base" {
  name     = var.kb_name
  role_arn = aws_iam_role.bedrock_kb_resource_kb.arn
  knowledge_base_configuration {
    vector_knowledge_base_configuration {
      embedding_model_arn = var.embedding_model_arn
    }
    type = "VECTOR"
  }
  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = var.collection_arn
      vector_index_name = var.vector_index_name
      field_mapping {
        vector_field   = var.vector_field
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }
  depends_on = [
    aws_iam_role_policy.bedrock_kb_resource_kb_model,
    aws_iam_role_policy.bedrock_kb_resource_kb_s3,
    aws_iam_role_policy.bedrock_kb_resource_kb_oss,
    var.storage_wait_id
  ]
}

resource "aws_bedrockagent_data_source" "this" {
  knowledge_base_id    = aws_bedrockagent_knowledge_base.knowledge_base.id
  name                 = "${var.kb_name}-s3-source"
  data_deletion_policy = "RETAIN"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = var.s3_source_arn
    }
  }

  vector_ingestion_configuration {
    custom_transformation_configuration {
      intermediate_storage {
        s3_location {
          uri = "s3://${aws_s3_bucket.intermediate.bucket}"
        }
      }
      transformation {
        step_to_apply = "POST_CHUNKING"
        transformation_function {
          transformation_lambda_configuration {
            lambda_arn = aws_lambda_function.enricher.arn
          }
        }
      }
    }

    chunking_configuration {
      chunking_strategy = var.chunking_strategy

      dynamic "fixed_size_chunking_configuration" {
        for_each = var.chunking_strategy == "FIXED_SIZE" ? [1] : []
        content {
          max_tokens         = var.fixed_size_max_tokens
          overlap_percentage = var.fixed_size_overlap_percentage
        }
      }

      dynamic "hierarchical_chunking_configuration" {
        for_each = var.chunking_strategy == "HIERARCHICAL" ? [1] : []
        content {
          overlap_tokens = var.hierarchical_overlap_tokens
          level_configuration {
            max_tokens = var.hierarchical_parent_max_tokens
          }
          level_configuration {
            max_tokens = var.hierarchical_child_max_tokens
          }
        }
      }

      dynamic "semantic_chunking_configuration" {
        for_each = var.chunking_strategy == "SEMANTIC" ? [1] : []
        content {
          buffer_size                     = var.semantic_buffer_size
          breakpoint_percentile_threshold = var.semantic_breakpoint_percentile_threshold
          max_token                       = var.semantic_max_tokens
        }
      }
    }
  }
}

