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
