data "aws_caller_identity" "this" {}
data "aws_partition" "this" {}
data "aws_region" "this" {}

locals {
  name_prefix            = "${var.project}-${var.environment}"
  account_id             = data.aws_caller_identity.this.account_id
  partition              = data.aws_partition.this.partition
  region                 = data.aws_region.this.id
  region_name_tokenized  = split("-", local.region)
  region_short           = "${substr(local.region_name_tokenized[0], 0, 2)}${substr(local.region_name_tokenized[1], 0, 1)}${local.region_name_tokenized[2]}"
  bedrock_model_arn      = "arn:${local.partition}:bedrock:${local.region}::foundation-model/${coalesce(var.kb_model_id, "amazon.titan-embed-text-v2:0")}"
  bedrock_kb_name        = coalesce(var.kb_name, "resourceKB")

  caller_identity_arn = (
    can(regex("assumed-role", data.aws_caller_identity.this.arn))
    ? replace(
    data.aws_caller_identity.this.arn,
    "/^arn:([^:]+):sts::([^:]+):assumed-role\\/([^\\/]+)\\/.+$/",
    "arn:$1:iam::$2:role/$3"
  )
    : data.aws_caller_identity.this.arn
  )

  common_tags = {
    ManagedBy  = "Terraform"
    Repository = "legalize-ai-poc"
  }
}
