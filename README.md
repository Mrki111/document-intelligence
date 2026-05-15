# Serverless AI Document Intelligence Pipeline

Serverless AWS document processing pipeline for small PDF documents. The MVP lets a client request a pre-signed S3 upload URL, upload a validated PDF, trigger Lambda processing from an S3 event, extract multi-page text with asynchronous Amazon Textract, and read the document status/result through API Gateway.

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
  -> Amazon Textract async job
  -> SNS completion notification
  -> Lambda complete_document_processing
  -> optional Amazon Bedrock
  -> DynamoDB status/result
  -> API Gateway GET /documents/{documentId}
```

## Features

- Pre-signed S3 upload URLs gated by validated upload metadata
- S3-event-driven async Textract extraction for multi-page PDFs
- Optional Amazon Bedrock analysis with per-document-type JSON schemas
- DynamoDB-backed status tracking with conditional updates
- Retry-safe duplicate-event handling, plus stale-PROCESSING recovery
- SNS-driven completion handler with paginated Textract result collection
- SQS dead-letter queue and CloudWatch alarm for unrecoverable completion failures
- Least-privilege IAM roles per Lambda
- CloudWatch log groups with retention, API Gateway throttling, and reserved concurrency

## MVP Constraints

- PDFs only.
- Maximum upload size defaults to 10 MB.
- Maximum page count defaults to 25 pages.
- `documentType` must be `resume`, `invoice`, or `general`.
- Invalid or oversized uploads are rejected before URL generation and checked again after upload.

## Local Development

```bash
python -m pip install -r requirements-dev.txt
ruff check backend tests
python -m unittest discover -s tests
```

## Deploy

Requires Terraform ≥ 1.6, an AWS account with credentials configured (`aws configure` or environment variables), Python 3.12, and `jq` for the demo script.

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
- `max_textract_pages`
- `bedrock_model_id`
- `stale_processing_seconds`
- `api_throttle_burst_limit`, `api_throttle_rate_limit`
- `process_document_reserved_concurrency`, default `-1` to leave Lambda reserved concurrency unset. Only set this if your account concurrency quota is high enough to keep at least 10 unreserved executions.
- `complete_document_processing_reserved_concurrency`, same convention for the Textract completion Lambda.
- `dlq_alarm_actions`, optional list of SNS topic ARNs to notify when the completion DLQ has messages.

Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` for local values.

## V2: Bedrock Analysis

V2 adds structured AI analysis after Textract extraction.

1. In the AWS console, open Amazon Bedrock in the same region as Terraform, default `us-east-1`.
2. Enable access to the model you want to use.
3. Set `bedrock_model_id` in `infra/terraform.tfvars`.
4. Run `terraform -chdir=infra apply`.
5. Upload a new PDF and poll `GET /documents/{documentId}`.

Example:

```hcl
bedrock_model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
```

The completed document response should include `extractedTextPreview`, `pageCount`, and `analysis`.

## API

Health check:

```bash
curl "$API_URL/health"
```

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

Poll for the result:

```bash
curl "$API_URL/documents/$DOCUMENT_ID"
```

The response shape evolves with the document status:

```jsonc
// PROCESSING — Textract job in flight
{ "documentId": "doc_…", "status": "PROCESSING" }

// COMPLETED — extracted text + optional Bedrock analysis
{
  "documentId": "doc_…",
  "status": "COMPLETED",
  "documentType": "general",
  "filename": "Q4_EC.pdf",
  "extractedTextPreview": "…first 1000 chars of OCR output…",
  "pageCount": 15,
  "analysis": { "summary": "…", "keyPoints": [], "risks": [], "…": "…" }
}

// FAILED — validation, Textract, or Bedrock error
{
  "documentId": "doc_…",
  "status": "FAILED",
  "failureReason": "INVALID_UPLOAD_SIZE",
  "errorMessage": "Uploaded object size does not match the request."
}
```

## Document lifecycle

```text
UPLOADED → PROCESSING → COMPLETED
                    ↘ FAILED
```

DynamoDB writes are guarded with conditional expressions: a duplicate S3 event will not overwrite a `COMPLETED` record, and a stale SNS notification (mismatched `textractJobId`) is ignored.

### DynamoDB record

| Attribute | Type | Present when |
|---|---|---|
| `documentId` | S | always (partition key) |
| `documentType`, `filename`, `contentType`, `contentLength` | S/S/S/N | always |
| `s3Key` | S | always |
| `status` | S | always (`UPLOADED` / `PROCESSING` / `COMPLETED` / `FAILED`) |
| `createdAt`, `updatedAt` | S | always (ISO-8601 UTC) |
| `expiresAt` | N | always (DynamoDB TTL epoch seconds) |
| `textractJobId`, `textractJobStartedAt`, `s3ETag` | S/S/S | once Textract started |
| `extractedTextPreview`, `extractedTextLength`, `pageCount` | S/N/N | `COMPLETED` |
| `analysis` | M | `COMPLETED`, if `bedrock_model_id` is set |
| `failureReason`, `errorMessage` | S/S | `FAILED` |

## Demo

A captured end-to-end run with evidence files is in [`docs/examples/`](docs/examples/), walked through in [`docs/journey.md`](docs/journey.md).

To reproduce, after `terraform apply`, supply a PDF and run the script. The script defaults to `./Q4_EC.pdf` (gitignored — bring your own) and `documentType=general`; override either via env vars:

```bash
PDF=/path/to/your.pdf ./scripts/demo.sh
# or
PDF=Q4_EC.pdf DOCUMENT_TYPE=resume ./scripts/demo.sh
```

Any PDF up to `max_content_length` (10 MB default) and within `max_textract_pages` (25 default) works. The captured `docs/examples/` run was generated from an Amazon Q4 2025 earnings-call transcript (15 pages), but the pipeline is content-agnostic.

The script:

1. Requests a presigned URL, uploads the PDF, polls until `COMPLETED`, and saves the final document record (with `extractedTextPreview`, `pageCount`, and `analysis` if Bedrock is enabled).
2. Sends an invalid `documentType` to show the pre-signature validation gate (HTTP 400).
3. Lies about `contentLength` in the upload request to trigger the post-upload S3 `HeadObject` revalidation, ending in `FAILED` with `INVALID_UPLOAD_SIZE`.

## Security Design

- Pre-signed PUT URLs replace any public-write surface on the S3 bucket.
- S3 bucket has public access blocked and AES-256 server-side encryption enabled.
- Lambdas run with per-function IAM roles scoped to specific resources and actions (S3 prefix, DynamoDB table, Textract, Bedrock).
- Textract publishes completion notifications to a private SNS topic through a scoped service role.
- The `process_document` Lambda's `iam:PassRole` is conditioned on `iam:PassedToService = textract.amazonaws.com`, so the Textract publish role can only be handed to Textract.
- The DLQ's SQS queue policy only allows the SNS service to publish, scoped to the Textract completion topic ARN.
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
- Optional reserved concurrency on `process_document` and `complete_document_processing`
- Configurable page-count cap after Textract completes
- Bedrock text-length cap before each `InvokeModel`
- Tear down with `terraform destroy` when not in use

## Lessons Learned

- Treat the pre-signed PUT URL as a delivery mechanism, not a validation boundary: revalidate the actual S3 object before Textract.
- DynamoDB conditional updates are the simplest way to make S3 event handlers idempotent without an external lock.
- Async Textract keeps Lambda duration predictable for multi-page PDFs; SNS is the handoff between OCR completion and result collection.
- Plan for stuck `PROCESSING` records up front; a stale-timestamp guard is cheap and prevents permanently wedged documents after a Lambda crash.
- Lambda IAM should be split per function; one shared role hides the actual blast radius of each handler.
- An SNS-to-Lambda subscription needs two DLQ paths: a Lambda async DLQ for runtime failures *and* an SNS subscription redrive for delivery failures. They cover different failure modes.

## Future Improvements

- SQS or EventBridge between S3 and `process_document` for retries and DLQ on the upstream side
- Step Functions to orchestrate extraction → analysis → indexing
- Cognito-backed authentication and per-user document history
- Pre-signed POST policies with `content-length-range` for server-side size enforcement
- Deployment automation and Terraform plan comments on pull requests
- Frontend UI and an OpenAPI spec for the HTTP API
