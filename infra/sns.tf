resource "aws_sns_topic" "textract_completion" {
  name = "AmazonTextract-${local.name_prefix}-completion"
  tags = local.common_tags
}

resource "aws_sns_topic_subscription" "complete_document_processing" {
  topic_arn = aws_sns_topic.textract_completion.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.functions["complete_document_processing"].arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.complete_document_processing_dlq.arn
  })

  depends_on = [
    aws_lambda_permission.allow_sns_complete_document_processing,
    aws_sqs_queue_policy.complete_document_processing_dlq,
  ]
}

resource "aws_sqs_queue" "complete_document_processing_dlq" {
  name                      = "${local.name_prefix}-complete-document-dlq"
  message_retention_seconds = 1209600
  tags                      = local.common_tags
}

data "aws_iam_policy_document" "complete_document_processing_dlq" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.complete_document_processing_dlq.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.textract_completion.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "complete_document_processing_dlq" {
  queue_url = aws_sqs_queue.complete_document_processing_dlq.url
  policy    = data.aws_iam_policy_document.complete_document_processing_dlq.json
}

resource "aws_cloudwatch_metric_alarm" "complete_document_processing_dlq_depth" {
  alarm_name          = "${local.name_prefix}-complete-document-dlq-depth"
  alarm_description   = "Messages in the complete_document_processing DLQ. Investigate and replay or purge."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.complete_document_processing_dlq.name
  }

  alarm_actions = var.dlq_alarm_actions
  ok_actions    = var.dlq_alarm_actions

  tags = local.common_tags
}
