terraform {
  required_providers {
    opensearch = {
      source  = "opensearch-project/opensearch"
      version = "2.3.2"
    }
  }
}
# OpenSearch collection access policy
resource "aws_opensearchserverless_access_policy" "resource_kb" {
  name = var.name
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource = [
            "index/${var.name}/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex", # Required for Terraform
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:UpdateIndex",
            "aoss:WriteDocument"
          ]
        },
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.name}"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DescribeCollectionItems",
            "aoss:UpdateCollectionItems"
          ]
        }
      ],
      Principal = [
        var.bedrock_iam_role_arn,
        var.aws_caller_identity_arn
      ]
    }
  ])
}

# OpenSearch collection data encryption policy
resource "aws_opensearchserverless_security_policy" "resource_kb_encryption" {
  name = var.name
  type = "encryption"
  policy = jsonencode({
    Rules = [
      {
        Resource = [
          "collection/${var.name}"
        ]
        ResourceType = "collection"
      }
    ],
    AWSOwnedKey = true
  })
}

# OpenSearch collection network policy
resource "aws_opensearchserverless_security_policy" "resource_kb_network" {
  name = var.name
  type = "network"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.name}"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/${var.name}"
          ]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# OpenSearch resource
resource "aws_opensearchserverless_collection" "resource_kb" {
  name = var.name
  type = "VECTORSEARCH"
  depends_on = [
    aws_opensearchserverless_access_policy.resource_kb,
    aws_opensearchserverless_security_policy.resource_kb_encryption,
    aws_opensearchserverless_security_policy.resource_kb_network
  ]
}

provider "opensearch" {
  url         = aws_opensearchserverless_collection.resource_kb.collection_endpoint
  healthcheck = false
}

# OpenSearch index creation
resource "opensearch_index" "resource_kb" {
  name                           = var.index_name
  number_of_shards               = "2"
  number_of_replicas             = "0"
  index_knn                      = true
  index_knn_algo_param_ef_search = "512"
  mappings                       = <<-EOF
    {
      "properties": {
        "bedrock-knowledge-base-default-vector": {
          "type": "knn_vector",
          "dimension": ${var.vector_dimension},
          "method": {
            "name": "hnsw",
            "engine": "faiss",
            "parameters": {
              "m": 16,
              "ef_construction": 512
            },
            "space_type": "l2"
          }
        },
        "AMAZON_BEDROCK_METADATA": {
          "type": "text",
          "index": "false"
        },
        "AMAZON_BEDROCK_TEXT_CHUNK": {
          "type": "text",
          "index": "true"
        }
      }
    }
  EOF
  force_destroy                  = true
  depends_on                     = [
    aws_opensearchserverless_collection.resource_kb,
    aws_opensearchserverless_access_policy.resource_kb,
    time_sleep.access_policy_propagation
  ]
}

resource "time_sleep" "access_policy_propagation" {
  depends_on = [
    aws_opensearchserverless_access_policy.resource_kb,
    aws_opensearchserverless_collection.resource_kb
  ]

  create_duration = "30s"
}

resource "time_sleep" "aws_iam_role_policy_bedrock_kb_resource_kb_oss" {
  create_duration = "20s"
}
