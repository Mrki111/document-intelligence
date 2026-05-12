# Serverless AI Document Intelligence Pipeline

Serverless AWS document processing pipeline for small PDF documents. The MVP lets a client request a pre-signed S3 upload URL, upload a validated single-page PDF, trigger Lambda processing from an S3 event, extract text with Amazon Textract, and read the document status/result through API Gateway.

Amazon Bedrock analysis is wired as an optional next step. Leave `bedrock_model_id` empty for the Version 1 Textract-only flow, or set it in Terraform when Bedrock model access is enabled.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full diagram. Summary flow:

```text
Client
  -> API Gateway POST /upload-url
  -> Lambda generate_upload_url
  -> DynamoDB document record
  -> S3 pre-signed PUT URL
  -> S3 ObjectCreated event
  -> Lambda process_document
  -> Amazon Textract
  -> optional Amazon Bedrock
  -> DynamoDB status/result
  -> API Gateway GET /documents/{documentId}
```

## Features

- Pre-signed S3 upload URLs gated by validated upload metadata
- S3-event-driven Textract extraction for single-page PDFs
- Optional Amazon Bedrock analysis with per-document-type JSON schemas
- DynamoDB-backed status tracking with conditional updates
- Retry-safe duplicate-event handling, plus stale-PROCESSING recovery
- Least-privilege IAM roles per Lambda
- CloudWatch log groups with retention, API Gateway throttling, and reserved concurrency

## MVP Constraints

- PDFs only.
- Single-page PDFs for the synchronous Textract MVP.
- Maximum upload size defaults to 10 MB.
- `documentType` must be `resume`, `invoice`, or `general`.
- Invalid or oversized uploads are rejected before URL generation and checked again after upload.

## Local Tests

```bash
PYTHONPATH=backend python -m unittest discover -s tests
```

## Deploy

```bash
cd infra
terraform init
terraform plan
terraform apply
```

Useful Terraform variables:

- `aws_region`
- `environment`
- `max_content_length`
- `record_ttl_days`
- `bedrock_model_id`
- `stale_processing_seconds`
- `api_throttle_burst_limit`, `api_throttle_rate_limit`
- `process_document_reserved_concurrency`, default `-1` to leave Lambda reserved concurrency unset. Only set this if your account concurrency quota is high enough to keep at least 10 unreserved executions.

Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` for local values.

## V2: Bedrock Analysis

V2 adds structured AI analysis after Textract extraction.

1. In the AWS console, open Amazon Bedrock in the same region as Terraform, default `us-east-1`.
2. Enable access to the model you want to use.
3. Set `bedrock_model_id` in `infra/terraform.tfvars`.
4. Run `terraform -chdir=infra apply`.
5. Upload a new single-page PDF and poll `GET /documents/{documentId}`.

Example:

```hcl
bedrock_model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
```

The completed document response should include both `extractedTextPreview` and `analysis`.

## API

Generate an upload URL:

```bash
curl -X POST "$API_URL/upload-url" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "resume.pdf",
    "documentType": "resume",
    "contentType": "application/pdf",
    "contentLength": 524288
  }'
```

Upload the PDF:

```bash
curl -X PUT "$UPLOAD_URL" \
  -H "Content-Type: application/pdf" \
  --upload-file resume.pdf
```

Get the result:

```bash
curl "$API_URL/documents/$DOCUMENT_ID"
```

## Security Design

- Pre-signed PUT URLs replace any public-write surface on the S3 bucket.
- S3 bucket has public access blocked and AES-256 server-side encryption enabled.
- Lambdas run with per-function IAM roles scoped to specific resources and actions (S3 prefix, DynamoDB table, Textract, Bedrock).
- Upload requests are validated twice: declared metadata before the URL is signed, and S3 `HeadObject` size + content type before Textract is called.
- DynamoDB writes use conditional expressions so duplicate S3 events cannot overwrite a `COMPLETED` record.
- API responses use safe error messages; stack traces stay in CloudWatch.
- No secrets in code; configuration flows through Terraform variables and Lambda environment variables.

## Cost Considerations

This project uses pay-per-use AWS services. Main variable costs come from Amazon Textract and Amazon Bedrock usage. The MVP is designed for small test documents and low-volume usage.

Cost controls already in the stack:

- DynamoDB on-demand billing and TTL cleanup for demo records
- S3 lifecycle expiration on the upload prefix
- API Gateway default-route throttling
- Optional reserved concurrency on `process_document`
- Bedrock text-length cap before each `InvokeModel`
- Tear down with `terraform destroy` when not in use

## Lessons Learned

- Treat the pre-signed PUT URL as a delivery mechanism, not a validation boundary: revalidate the actual S3 object before Textract.
- DynamoDB conditional updates are the simplest way to make S3 event handlers idempotent without an external lock.
- Plan for stuck `PROCESSING` records up front; a stale-timestamp guard is cheap and prevents permanently wedged documents after a Lambda crash.
- Lambda IAM should be split per function; one shared role hides the actual blast radius of each handler.

## Future Improvements

- Async Textract for multi-page or large PDFs
- SQS or EventBridge between S3 and Lambda for retries and DLQ
- Step Functions to orchestrate extraction → analysis → indexing
- Cognito-backed authentication and per-user document history
- Pre-signed POST policies with `content-length-range` for server-side size enforcement
- CI/CD via GitHub Actions, including Terraform plan checks
- Frontend UI and an OpenAPI spec for the HTTP API
