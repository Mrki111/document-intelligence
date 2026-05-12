resource "aws_s3_bucket" "uploads" {
  bucket        = substr("${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.aws_region}", 0, 63)
  force_destroy = true

  tags = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  rule {
    id     = "expire-demo-uploads"
    status = "Enabled"

    filter {
      prefix = local.upload_prefix
    }

    expiration {
      days = var.record_ttl_days
    }
  }
}

resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.functions["process_document"].arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.upload_prefix
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.allow_s3_process_document]
}
