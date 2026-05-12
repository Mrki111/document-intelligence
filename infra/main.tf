terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  project_slug  = lower(replace(var.project_name, "_", "-"))
  name_prefix   = "${local.project_slug}-${var.environment}"
  upload_prefix = "uploads/"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  lambdas = {
    generate_upload_url = {
      handler     = "lambdas.generate_upload_url.app.lambda_handler"
      timeout     = 10
      memory_size = 128
      role_arn    = aws_iam_role.generate_upload_url.arn
    }
    process_document = {
      handler     = "lambdas.process_document.app.lambda_handler"
      timeout     = 60
      memory_size = 512
      role_arn    = aws_iam_role.process_document.arn
    }
    get_document = {
      handler     = "lambdas.get_document.app.lambda_handler"
      timeout     = 10
      memory_size = 128
      role_arn    = aws_iam_role.get_document.arn
    }
    health = {
      handler     = "lambdas.health.app.lambda_handler"
      timeout     = 5
      memory_size = 128
      role_arn    = aws_iam_role.health.arn
    }
  }
}
