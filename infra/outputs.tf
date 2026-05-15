output "api_endpoint" {
  description = "Base URL for the HTTP API."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "upload_bucket_name" {
  description = "S3 bucket for uploaded documents."
  value       = aws_s3_bucket.uploads.bucket
}

output "document_table_name" {
  description = "DynamoDB table storing document status and results."
  value       = aws_dynamodb_table.documents.name
}

output "textract_completion_topic_arn" {
  description = "SNS topic used by Textract async completion notifications."
  value       = aws_sns_topic.textract_completion.arn
}

output "complete_document_processing_dlq_url" {
  description = "SQS DLQ URL for the complete_document_processing Lambda."
  value       = aws_sqs_queue.complete_document_processing_dlq.url
}
