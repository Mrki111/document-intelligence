data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "generate_upload_url" {
  name               = "${local.name_prefix}-generate-upload-url"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "process_document" {
  name               = "${local.name_prefix}-process-document"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "complete_document_processing" {
  name               = "${local.name_prefix}-complete-document"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "get_document" {
  name               = "${local.name_prefix}-get-document"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role" "health" {
  name               = "${local.name_prefix}-health"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  for_each = {
    generate_upload_url          = aws_iam_role.generate_upload_url.name
    process_document             = aws_iam_role.process_document.name
    complete_document_processing = aws_iam_role.complete_document_processing.name
    get_document                 = aws_iam_role.get_document.name
    health                       = aws_iam_role.health.name
  }

  role       = each.value
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "generate_upload_url" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.uploads.arn}/${local.upload_prefix}*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
    ]
    resources = [aws_dynamodb_table.documents.arn]
  }
}

resource "aws_iam_policy" "generate_upload_url" {
  name   = "${local.name_prefix}-generate-upload-url"
  policy = data.aws_iam_policy_document.generate_upload_url.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "generate_upload_url" {
  role       = aws_iam_role.generate_upload_url.name
  policy_arn = aws_iam_policy.generate_upload_url.arn
}

data "aws_iam_policy_document" "process_document" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.uploads.arn}/${local.upload_prefix}*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "textract:StartDocumentTextDetection",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "iam:PassRole",
    ]
    resources = [aws_iam_role.textract_publish.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["textract.amazonaws.com"]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.documents.arn]
  }
}

resource "aws_iam_policy" "process_document" {
  name   = "${local.name_prefix}-process-document"
  policy = data.aws_iam_policy_document.process_document.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "process_document" {
  role       = aws_iam_role.process_document.name
  policy_arn = aws_iam_policy.process_document.arn
}

data "aws_iam_policy_document" "complete_document_processing" {
  statement {
    effect = "Allow"
    actions = [
      "textract:GetDocumentTextDetection",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.documents.arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
    ]
    resources = [aws_sqs_queue.complete_document_processing_dlq.arn]
  }
}

resource "aws_iam_policy" "complete_document_processing" {
  name   = "${local.name_prefix}-complete-document"
  policy = data.aws_iam_policy_document.complete_document_processing.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "complete_document_processing" {
  role       = aws_iam_role.complete_document_processing.name
  policy_arn = aws_iam_policy.complete_document_processing.arn
}

data "aws_iam_policy_document" "get_document" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
    ]
    resources = [aws_dynamodb_table.documents.arn]
  }
}

resource "aws_iam_policy" "get_document" {
  name   = "${local.name_prefix}-get-document"
  policy = data.aws_iam_policy_document.get_document.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "get_document" {
  role       = aws_iam_role.get_document.name
  policy_arn = aws_iam_policy.get_document.arn
}

data "aws_iam_policy_document" "textract_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["textract.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "textract_publish" {
  name               = "${local.name_prefix}-textract-publish"
  assume_role_policy = data.aws_iam_policy_document.textract_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "textract_publish" {
  statement {
    effect = "Allow"
    actions = [
      "sns:Publish",
    ]
    resources = [aws_sns_topic.textract_completion.arn]
  }
}

resource "aws_iam_policy" "textract_publish" {
  name   = "${local.name_prefix}-textract-publish"
  policy = data.aws_iam_policy_document.textract_publish.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "textract_publish" {
  role       = aws_iam_role.textract_publish.name
  policy_arn = aws_iam_policy.textract_publish.arn
}
