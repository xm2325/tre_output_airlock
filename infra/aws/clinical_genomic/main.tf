provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      DataClass   = "synthetic-demo"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  buckets = {
    landing    = "${local.name_prefix}-landing"
    quarantine = "${local.name_prefix}-quarantine"
    curated    = "${local.name_prefix}-curated"
    restricted = "${local.name_prefix}-restricted"
  }
}

resource "aws_kms_key" "data" {
  description             = "Clinical-genomic demonstration data encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

resource "aws_s3_bucket" "data" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "data" {
  for_each = aws_s3_bucket.data

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.data.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  for_each = aws_s3_bucket.data

  bucket = each.value.id

  rule {
    id     = "abort-incomplete-multipart-upload"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name_prefix}-dead-letter"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.data.arn
}

resource "aws_sqs_queue" "delivery" {
  name                       = "${local.name_prefix}-delivery"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600
  kms_master_key_id          = aws_kms_key.data.arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid = "ReadLandingAndWriteControlledZones"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket",
      "s3:PutObject",
    ]
    resources = concat(
      [for bucket in aws_s3_bucket.data : bucket.arn],
      [for bucket in aws_s3_bucket.data : "${bucket.arn}/*"],
    )
  }

  statement {
    sid = "UseDataKey"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.data.arn]
  }

  statement {
    sid = "ProcessDeliveryQueue"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.delivery.arn]
  }
}

resource "aws_iam_policy" "pipeline" {
  name   = "${local.name_prefix}-pipeline"
  policy = data.aws_iam_policy_document.pipeline.json
}
