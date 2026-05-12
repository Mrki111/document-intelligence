variable "project_name" {
  description = "Project name used for resource naming and tags."
  type        = string
  default     = "document-intelligence"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-1"
}

variable "lambda_runtime" {
  description = "Python Lambda runtime."
  type        = string
  default     = "python3.12"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 14
}

variable "max_content_length" {
  description = "Maximum accepted upload size in bytes for the synchronous Textract MVP."
  type        = number
  default     = 10485760
}

variable "upload_url_expiration_seconds" {
  description = "Pre-signed upload URL expiration in seconds."
  type        = number
  default     = 900
}

variable "record_ttl_days" {
  description = "Number of days before demo records expire from DynamoDB."
  type        = number
  default     = 7
}

variable "allowed_document_types" {
  description = "Supported document types."
  type        = list(string)
  default     = ["resume", "invoice", "general"]
}

variable "bedrock_model_id" {
  description = "Optional Bedrock model ID. Leave empty for the Version 1 Textract-only MVP."
  type        = string
  default     = ""
}

variable "bedrock_text_limit" {
  description = "Maximum number of extracted text characters sent to Bedrock."
  type        = number
  default     = 12000
}

variable "api_throttle_burst_limit" {
  description = "API Gateway default route burst limit."
  type        = number
  default     = 20
}

variable "api_throttle_rate_limit" {
  description = "API Gateway default route steady-state requests per second."
  type        = number
  default     = 10
}

variable "process_document_reserved_concurrency" {
  description = "Reserved concurrency for the document processing Lambda. Use -1 to leave it unset, which is required for accounts with the default 10-concurrency quota."
  type        = number
  default     = -1
}

variable "stale_processing_seconds" {
  description = "Age after which a PROCESSING record may be retried by a duplicate S3 event."
  type        = number
  default     = 600
}
