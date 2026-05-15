data "archive_file" "backend" {
  type        = "zip"
  source_dir  = "${path.module}/../backend"
  output_path = "${path.module}/build/backend.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc", "**/*.egg-info/**"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambdas

  name              = "/aws/lambda/${local.name_prefix}-${each.key}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "functions" {
  for_each = local.lambdas

  function_name    = "${local.name_prefix}-${each.key}"
  role             = each.value.role_arn
  handler          = each.value.handler
  runtime          = var.lambda_runtime
  filename         = data.archive_file.backend.output_path
  source_code_hash = data.archive_file.backend.output_base64sha256
  timeout          = each.value.timeout
  memory_size      = each.value.memory_size
  reserved_concurrent_executions = (
    each.key == "process_document" ? var.process_document_reserved_concurrency :
    each.key == "complete_document_processing" ? var.complete_document_processing_reserved_concurrency :
    null
  )

  environment {
    variables = merge(
      {
        UPLOAD_BUCKET                 = aws_s3_bucket.uploads.bucket
        TABLE_NAME                    = aws_dynamodb_table.documents.name
        ALLOWED_DOCUMENT_TYPES        = join(",", var.allowed_document_types)
        MAX_CONTENT_LENGTH            = tostring(var.max_content_length)
        UPLOAD_PREFIX                 = local.upload_prefix
        UPLOAD_URL_EXPIRATION_SECONDS = tostring(var.upload_url_expiration_seconds)
        RECORD_TTL_DAYS               = tostring(var.record_ttl_days)
        BEDROCK_MODEL_ID              = var.bedrock_model_id
        BEDROCK_TEXT_LIMIT            = tostring(var.bedrock_text_limit)
        STALE_PROCESSING_SECONDS      = tostring(var.stale_processing_seconds)
      },
      each.value.environment,
    )
  }

  dynamic "dead_letter_config" {
    for_each = each.key == "complete_document_processing" ? [aws_sqs_queue.complete_document_processing_dlq.arn] : []
    content {
      target_arn = dead_letter_config.value
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.generate_upload_url,
    aws_iam_role_policy_attachment.process_document,
    aws_iam_role_policy_attachment.complete_document_processing,
    aws_iam_role_policy_attachment.get_document,
  ]

  tags = local.common_tags
}

resource "aws_lambda_permission" "allow_s3_process_document" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.functions["process_document"].function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.uploads.arn
}

resource "aws_lambda_permission" "allow_sns_complete_document_processing" {
  statement_id  = "AllowExecutionFromTextractSns"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.functions["complete_document_processing"].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.textract_completion.arn
}
