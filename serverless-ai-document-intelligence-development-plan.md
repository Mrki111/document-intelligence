# Serverless AI Document Intelligence Pipeline — Development Plan

## 1. Project Goal

Build a serverless AWS application that allows users to upload PDF documents, automatically extract text, analyze the content with AI, and retrieve structured results through an API.

The project demonstrates practical AI cloud engineering skills using AWS serverless architecture, AI services, infrastructure as code, IAM security, and observability.

## 2. Target Portfolio Description

**Project Name:** Serverless AI Document Intelligence Pipeline on AWS

**Short Description:**
A serverless document processing pipeline where users upload PDF files through pre-signed S3 URLs. Uploaded files trigger an AWS Lambda function that extracts text using Amazon Textract, analyzes the extracted content with Amazon Bedrock, and stores structured results in DynamoDB. Results are exposed through API Gateway.

**Main Skills Demonstrated:**

- AWS serverless architecture
- S3 event-driven processing
- Lambda-based backend development
- API Gateway API design
- DynamoDB data modeling
- Amazon Textract document extraction
- Amazon Bedrock AI analysis
- IAM least-privilege permissions
- CloudWatch logging
- Terraform infrastructure as code
- Cost-aware cloud design

---

## 3. Architecture Overview

```text
Client / Postman / Frontend
        |
        | POST /upload-url
        v
API Gateway
        |
        v
Lambda: generate_upload_url
        |
        v
DynamoDB: create document record
        |
        v
S3 pre-signed upload URL
        |
        v
Client uploads PDF to S3
        |
        v
S3 ObjectCreated event
        |
        v
Lambda: process_document
        |
        v
Amazon Textract: extract text
        |
        v
Amazon Bedrock: analyze document
        |
        v
DynamoDB: store result
        |
        v
GET /documents/{documentId}
```

---

## 4. AWS Services Used

| Service | Purpose |
|---|---|
| Amazon S3 | Store uploaded PDF documents |
| AWS Lambda | Run backend and processing logic |
| API Gateway | Expose HTTP API endpoints |
| DynamoDB | Store document metadata, status, and AI analysis |
| Amazon Textract | Extract text from uploaded documents |
| Amazon Bedrock | Analyze extracted document text with AI |
| IAM | Manage least-privilege permissions |
| CloudWatch | Store logs and monitor Lambda execution |
| Terraform | Provision infrastructure as code |

---

## 5. MVP Scope

The first version should be simple and functional.

### MVP Features

- Generate pre-signed S3 upload URLs
- Upload PDF documents to S3
- Trigger Lambda when a document is uploaded
- Extract text from uploaded single-page PDFs using synchronous Textract
- Store processing status in DynamoDB
- Retrieve document result by document ID
- Log processing events in CloudWatch
- Enforce basic upload validation for file type, declared file size, and document type

### MVP Constraints

- Version 1 uses synchronous Textract, so accepted PDFs must be single-page documents.
- Keep the maximum accepted file size at 10 MB or less for the synchronous Textract MVP.
- Reject invalid file extensions, invalid `Content-Type` values, unsupported `documentType` values, and oversized uploads before processing.
- Verify uploaded object metadata in `process_document` before calling Textract, because a pre-signed PUT URL alone should not be treated as full validation.

### MVP Exclusions

Do not build these at the start:

- Frontend UI
- Authentication
- Multi-user accounts
- Advanced file management
- Multipage or large-document async Textract jobs
- Kubernetes or containers
- CI/CD pipeline

Build those later only after the basic pipeline works.

---

## 6. Project Versions

## Version 1 — Basic Serverless Document Processing

### Goal

Upload a small single-page PDF, extract text with synchronous Textract, and store the extracted text preview in DynamoDB.

### Services

- S3
- Lambda
- API Gateway
- DynamoDB
- Textract
- CloudWatch
- IAM

### Tasks

- [ ] Create GitHub repository
- [ ] Add initial Terraform project structure
- [ ] Create S3 bucket for uploads with Terraform
- [ ] Create DynamoDB table with Terraform
- [ ] Create `generate_upload_url` Lambda
- [ ] Connect `generate_upload_url` to API Gateway
- [ ] Validate filename, extension, `contentType`, `contentLength`, and `documentType`
- [ ] Test pre-signed upload URL with curl or Postman
- [ ] Create `process_document` Lambda
- [ ] Configure S3 event trigger with an upload prefix and `.pdf` suffix filter
- [ ] Verify uploaded object metadata before processing
- [ ] Add idempotency handling for duplicate S3 events and Lambda retries
- [ ] Call synchronous Textract from `process_document`
- [ ] Store extracted text preview in DynamoDB
- [ ] Create `get_document` Lambda
- [ ] Connect `get_document` to API Gateway
- [ ] Test full flow end-to-end

### Completion Criteria

The system can:

1. Generate an upload URL
2. Accept a PDF upload
3. Trigger processing automatically
4. Extract text
5. Store status and extracted text preview
6. Return the document result through an API
7. Reject invalid or oversized uploads safely
8. Avoid overwriting a completed result when duplicate S3 events occur

---

## Version 2 — AI Analysis with Amazon Bedrock

### Goal

Add AI analysis after text extraction.

### Services Added

- Amazon Bedrock

### Supported Document Types

Start with three types:

- `resume`
- `invoice`
- `general`

### Tasks

- [ ] Enable Amazon Bedrock model access in AWS account
- [ ] Choose a Bedrock model, such as Claude through Amazon Bedrock
- [ ] Add `documentType` field to upload request
- [ ] Create prompts for resume analysis
- [ ] Create prompts for invoice extraction
- [ ] Create prompts for general document summarization
- [ ] Call Bedrock from `process_document`
- [ ] Parse Bedrock response as JSON
- [ ] Validate Bedrock JSON against the expected schema for each document type
- [ ] Limit or chunk extracted text before sending it to Bedrock
- [ ] Store AI analysis in DynamoDB
- [ ] Add error handling for invalid model output
- [ ] Test all supported document types

### Completion Criteria

The system can:

1. Extract text from a document
2. Send the extracted text to Bedrock
3. Receive structured JSON analysis
4. Store the result in DynamoDB
5. Return the analysis through the API

---

## Version 3 — Portfolio-Grade Cloud Project

### Goal

Make the project professional enough for GitHub, portfolio, and interviews.

### Tasks

- [ ] Refine Terraform modules, variables, outputs, and deployment instructions
- [ ] Add least-privilege IAM roles per Lambda
- [ ] Enable S3 server-side encryption
- [ ] Block public access on S3 bucket
- [ ] Add CloudWatch log groups
- [ ] Add structured logging in Lambda functions
- [ ] Add failed status handling in DynamoDB
- [ ] Add input validation for file type and document type
- [ ] Add S3 lifecycle cleanup for uploaded test files
- [ ] Add DynamoDB TTL for old demo records
- [ ] Add API Gateway throttling
- [ ] Add Lambda reserved concurrency limits for cost protection
- [ ] Add cost considerations section to README
- [ ] Add security considerations section to README
- [ ] Add architecture diagram
- [ ] Add screenshots or demo GIF
- [ ] Add deployment instructions
- [ ] Add cleanup instructions

### Completion Criteria

The repository includes:

1. Working application code
2. Terraform infrastructure
3. Clear README
4. Architecture diagram
5. Security notes
6. Cost notes
7. Demo screenshots
8. Deployment and cleanup instructions

---

## 7. API Design

## Endpoint 1: Generate Upload URL

```text
POST /upload-url
```

### Request

```json
{
  "filename": "resume.pdf",
  "documentType": "resume",
  "contentType": "application/pdf",
  "contentLength": 524288
}
```

### Response

```json
{
  "documentId": "doc_abc123",
  "uploadUrl": "https://presigned-s3-url...",
  "s3Key": "uploads/doc_abc123/resume.pdf"
}
```

### Validation Rules

- `filename` must end with `.pdf`.
- `contentType` must be `application/pdf`.
- `contentLength` must be greater than 0 and less than or equal to the configured MVP maximum, such as 10 MB.
- `documentType` must be one of `resume`, `invoice`, or `general`.
- Generated S3 keys must use a controlled prefix such as `uploads/{documentId}/`.
- For stronger S3-side file size enforcement in a future version, consider using a pre-signed POST policy with a `content-length-range` condition. For the MVP, validate the declared size before issuing the URL and verify the uploaded S3 object before processing.

---

## Endpoint 2: Get Document Result

```text
GET /documents/{documentId}
```

### Processing Response

```json
{
  "documentId": "doc_abc123",
  "status": "PROCESSING"
}
```

### Completed Response

```json
{
  "documentId": "doc_abc123",
  "status": "COMPLETED",
  "documentType": "resume",
  "filename": "resume.pdf",
  "extractedTextPreview": "John Smith Cloud Engineer...",
  "analysis": {
    "summary": "Cloud engineer with AWS and Python experience.",
    "candidateLevel": "Junior to mid-level",
    "skills": ["AWS", "Python", "Docker"],
    "awsServicesMentioned": ["S3", "Lambda"],
    "strengths": ["Relevant cloud project experience"],
    "weaknesses": ["Limited production monitoring experience"],
    "missingKeywords": ["Terraform", "Kubernetes", "CI/CD"],
    "recommendedProjects": ["Build a serverless AI document pipeline"],
    "atsScore": 76
  }
}
```

---

## Endpoint 3: Health Check

```text
GET /health
```

### Response

```json
{
  "status": "ok"
}
```

---

## 8. DynamoDB Data Model

## Table Name

```text
DocumentAnalysis
```

## Primary Key

```text
documentId
```

## Example Item

```json
{
  "documentId": "doc_abc123",
  "documentType": "resume",
  "filename": "resume.pdf",
  "contentType": "application/pdf",
  "contentLength": 524288,
  "s3Key": "uploads/doc_abc123/resume.pdf",
  "status": "COMPLETED",
  "createdAt": "2026-05-12T12:00:00Z",
  "updatedAt": "2026-05-12T12:02:00Z",
  "s3ETag": "\"abc123etag\"",
  "extractedTextPreview": "John Smith Cloud Engineer...",
  "analysis": {
    "summary": "Cloud engineer with AWS and Python experience.",
    "candidateLevel": "Junior to mid-level",
    "skills": ["AWS", "Python", "Docker"],
    "awsServicesMentioned": ["S3", "Lambda"],
    "strengths": ["Relevant cloud project experience"],
    "weaknesses": ["Limited production monitoring experience"],
    "missingKeywords": ["Terraform", "Kubernetes", "CI/CD"],
    "recommendedProjects": ["Build a serverless AI document pipeline"],
    "atsScore": 76
  }
}
```

## Status Values

```text
UPLOADED
PROCESSING
COMPLETED
FAILED
```

For `FAILED` records, store a short `failureReason` value and a human-readable `errorMessage` that is safe to return or log.

---

## 9. Lambda Functions

## Lambda 1: `generate_upload_url`

### Purpose

Creates a document record and returns a pre-signed S3 upload URL.

### Responsibilities

- Validate request body
- Validate file type
- Validate document type
- Validate declared file size
- Generate `documentId`
- Create S3 key
- Insert initial item into DynamoDB
- Generate pre-signed S3 upload URL
- Return upload URL to client

### Required IAM Permissions

```text
s3:PutObject
dynamodb:PutItem
logs:CreateLogGroup
logs:CreateLogStream
logs:PutLogEvents
```

---

## Lambda 2: `process_document`

### Purpose

Processes uploaded documents after S3 upload.

### Responsibilities

- Receive S3 ObjectCreated event
- Extract `documentId` from S3 key
- Load the corresponding DynamoDB record
- Exit safely if the document is already `COMPLETED`
- Use conditional DynamoDB updates so duplicate events do not overwrite a successful result
- Verify uploaded object size, content type, and key before processing
- Update DynamoDB status to `PROCESSING`
- Extract text using synchronous Textract for MVP-supported single-page PDFs
- Send extracted text to Bedrock
- Parse structured JSON AI response
- Store analysis in DynamoDB
- Update status to `COMPLETED`
- On error, update status to `FAILED` with a safe failure reason

### Required IAM Permissions

```text
s3:GetObject
textract:DetectDocumentText
bedrock:InvokeModel
dynamodb:GetItem
dynamodb:UpdateItem
logs:CreateLogGroup
logs:CreateLogStream
logs:PutLogEvents
```

---

## Lambda 3: `get_document`

### Purpose

Returns the current status and analysis result for a document.

### Responsibilities

- Read `documentId` from path parameter
- Query DynamoDB
- Return document item
- Return 404 if document does not exist

### Required IAM Permissions

```text
dynamodb:GetItem
logs:CreateLogGroup
logs:CreateLogStream
logs:PutLogEvents
```

---

## Lambda 4: `health`

### Purpose

Simple health check endpoint.

### Responsibilities

- Return status `ok`

---

## 10. Bedrock Prompt Templates

## Resume Analysis Prompt

```text
Analyze this resume for a cloud engineering or AI cloud engineering role.

Return only valid JSON with this structure:

{
  "summary": string,
  "candidateLevel": string,
  "skills": string[],
  "awsServicesMentioned": string[],
  "strengths": string[],
  "weaknesses": string[],
  "missingKeywords": string[],
  "recommendedProjects": string[],
  "atsScore": number
}

Rules:
- Return only valid JSON.
- Do not include markdown.
- Do not invent experience.
- If information is missing, return null or an empty array.
- atsScore must be between 0 and 100.
```

---

## Invoice Extraction Prompt

```text
Extract invoice information from this document.

Return only valid JSON with this structure:

{
  "vendorName": string,
  "invoiceNumber": string,
  "invoiceDate": string,
  "dueDate": string,
  "currency": string,
  "totalAmount": number,
  "lineItems": [
    {
      "description": string,
      "quantity": number,
      "unitPrice": number,
      "amount": number
    }
  ],
  "missingFields": string[]
}

Rules:
- Return only valid JSON.
- Do not include markdown.
- Do not invent values.
- If a value is not present, return null.
```

---

## General Document Prompt

```text
Analyze this document.

Return only valid JSON with this structure:

{
  "title": string,
  "summary": string,
  "keyPoints": string[],
  "actionItems": string[],
  "risks": string[],
  "entities": string[]
}

Rules:
- Return only valid JSON.
- Do not include markdown.
- Do not invent information.
- Keep the summary under 150 words.
```

---

## 11. Repository Structure

```text
serverless-ai-document-intelligence/
  backend/
    lambdas/
      generate_upload_url/
        app.py
      process_document/
        app.py
      get_document/
        app.py
      health/
        app.py
    shared/
      prompts.py
      response.py
  infra/
    main.tf
    variables.tf
    outputs.tf
    iam.tf
    lambda.tf
    api_gateway.tf
    s3.tf
    dynamodb.tf
  docs/
    architecture.png
  tests/
    sample_resume.pdf
    sample_invoice.pdf
  README.md
```

---

## 12. Terraform Resources

Minimum Terraform resources:

```text
aws_s3_bucket
aws_s3_bucket_server_side_encryption_configuration
aws_s3_bucket_public_access_block
aws_s3_bucket_lifecycle_configuration
aws_dynamodb_table
aws_lambda_function
aws_iam_role
aws_iam_policy
aws_iam_role_policy_attachment
aws_apigatewayv2_api
aws_apigatewayv2_stage
aws_apigatewayv2_route
aws_apigatewayv2_integration
aws_lambda_permission
aws_s3_bucket_notification
aws_cloudwatch_log_group
```

---

## 13. Testing Plan

## Test 1: Generate Upload URL

```bash
curl -X POST https://YOUR_API_URL/upload-url \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "resume.pdf",
    "documentType": "resume",
    "contentType": "application/pdf",
    "contentLength": 524288
  }'
```

Expected result:

```json
{
  "documentId": "doc_abc123",
  "uploadUrl": "https://presigned-s3-url...",
  "s3Key": "uploads/doc_abc123/resume.pdf"
}
```

---

## Test 2: Upload PDF

```bash
curl -X PUT "PASTE_UPLOAD_URL_HERE" \
  -H "Content-Type: application/pdf" \
  --upload-file resume.pdf
```

Expected result:

- File appears in S3
- S3 event triggers Lambda
- DynamoDB status changes to `PROCESSING`

---

## Test 3: Get Document Result

```bash
curl https://YOUR_API_URL/documents/doc_abc123
```

Expected result during processing:

```json
{
  "documentId": "doc_abc123",
  "status": "PROCESSING"
}
```

Expected result after processing:

```json
{
  "documentId": "doc_abc123",
  "status": "COMPLETED",
  "analysis": {
    "summary": "...",
    "skills": ["AWS", "Python", "Docker"],
    "atsScore": 76
  }
}
```

---

## Test 4: Invalid Upload Request

```bash
curl -X POST https://YOUR_API_URL/upload-url \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "resume.exe",
    "documentType": "resume",
    "contentType": "application/octet-stream",
    "contentLength": 20971520
  }'
```

Expected result:

- API returns a 400 response
- No DynamoDB document record is created
- No upload URL is returned

---

## Test 5: Duplicate Processing Event

Simulate or replay the same S3 event for a completed document.

Expected result:

- `process_document` exits without reprocessing the file
- Existing `COMPLETED` analysis is not overwritten
- Logs clearly show the duplicate event was ignored

---

## Automated Tests

Add focused unit tests for:

- Request validation in `generate_upload_url`
- S3 event parsing in `process_document`
- Textract block parsing into plain text
- Bedrock JSON parsing and schema validation
- DynamoDB status transitions and duplicate-event handling

---

## 14. Security Requirements

Implement and document these:

- S3 public access blocked
- Pre-signed S3 upload URLs instead of public uploads
- Least-privilege IAM roles for each Lambda
- No hardcoded secrets in code
- Environment variables for configuration
- S3 server-side encryption enabled
- CloudWatch logs enabled
- File type validation
- Document type validation
- Declared and actual file size validation
- S3 event prefix and suffix filters
- Conditional DynamoDB updates to avoid overwriting completed results
- Safe error messages that do not expose internal stack traces through the API

---

## 15. Cost Considerations

Keep costs low by:

- Using serverless services
- Using DynamoDB on-demand billing
- Limiting accepted file size
- Testing with small PDFs
- Avoiding unnecessary frontend hosting at first
- Deleting test documents from S3
- Destroying infrastructure with Terraform after testing if needed
- Adding S3 lifecycle expiration for uploaded demo documents
- Adding DynamoDB TTL for old demo records
- Adding API Gateway throttling
- Adding Lambda reserved concurrency limits
- Capping the amount of extracted text sent to Bedrock

Mention in README:

```text
This project uses pay-per-use AWS services. Main variable costs come from Amazon Textract and Amazon Bedrock usage. The MVP is designed for small test documents and low-volume usage.
```

---

## 16. GitHub README Requirements

Your README should include:

- Project overview
- Architecture diagram
- Features
- AWS services used
- API endpoints
- Deployment instructions
- Testing instructions
- Security design
- Cost considerations
- Screenshots or demo GIF
- Lessons learned
- Future improvements

---

## 17. Portfolio Case Study Template

Use this structure on your portfolio website:

## Problem

Manual document review is slow and repetitive. This project automates text extraction and AI-based document analysis using AWS serverless services.

## Solution

I built a serverless document intelligence pipeline using S3, Lambda, Textract, Bedrock, DynamoDB, API Gateway, IAM, and CloudWatch.

## Architecture

User uploads a PDF using a pre-signed S3 URL. S3 triggers a Lambda function, which extracts text with Textract, sends it to Bedrock for structured analysis, and stores the result in DynamoDB. Users retrieve the result through API Gateway.

## Result

The MVP supports automated analysis of small single-page PDF resumes, invoices, and general documents with structured JSON outputs. Larger multipage documents are a planned async Textract upgrade.

## What I Learned

- Event-driven serverless architecture
- Document extraction with Textract
- AI inference with Bedrock
- DynamoDB status tracking
- IAM least-privilege design
- Terraform-based infrastructure deployment

---

## 18. Interview Explanation

Use this explanation:

```text
I built a serverless AI document intelligence pipeline on AWS. Users upload validated small PDFs through pre-signed S3 URLs. The upload triggers a Lambda function through an S3 event. The Lambda function extracts document text with synchronous Amazon Textract for the MVP, sends the extracted text to Amazon Bedrock for structured analysis, and stores the result in DynamoDB. The result can be retrieved through an API Gateway endpoint. I used CloudWatch for logs, least-privilege IAM roles for security, cost guardrails, retry-safe DynamoDB status updates, and Terraform to provision the infrastructure.
```

---

## 19. Build Order Checklist

Follow this exact order:

- [ ] Create GitHub repository
- [ ] Add initial README
- [ ] Create basic folder structure
- [ ] Add Terraform provider, variables, outputs, and remote-safe local state guidance
- [ ] Create S3 bucket with encryption, public access block, and lifecycle cleanup in Terraform
- [ ] Create DynamoDB table with on-demand billing and TTL in Terraform
- [ ] Create `generate_upload_url` Lambda
- [ ] Add API Gateway route for `POST /upload-url`
- [ ] Add upload request validation for filename, content type, content length, and document type
- [ ] Test valid and invalid upload URL generation
- [ ] Upload PDF to S3 with curl
- [ ] Create `process_document` Lambda
- [ ] Add S3 trigger with upload prefix and `.pdf` suffix filters
- [ ] Test S3 trigger
- [ ] Add uploaded object metadata validation
- [ ] Add duplicate-event and retry-safe status transitions
- [ ] Add synchronous Textract extraction for single-page PDFs
- [ ] Store extracted text preview in DynamoDB
- [ ] Create `get_document` Lambda
- [ ] Add API Gateway route for `GET /documents/{documentId}`
- [ ] Test document result retrieval
- [ ] Add Bedrock analysis
- [ ] Add extracted text length limits before Bedrock calls
- [ ] Add JSON schema validation for Bedrock responses
- [ ] Store structured AI output in DynamoDB
- [ ] Add error handling and failed status
- [ ] Add CloudWatch logging improvements
- [ ] Add API throttling and Lambda reserved concurrency
- [ ] Add architecture diagram
- [ ] Add screenshots or demo GIF
- [ ] Finalize README
- [ ] Add project to CV
- [ ] Add project to portfolio website

---

## 20. Future Improvements

Possible future upgrades:

- Add frontend UI
- Add authentication with Amazon Cognito
- Add user-specific document history
- Add async Textract jobs for larger PDFs
- Add SQS between S3 and Lambda for reliability
- Add dead-letter queue for failed processing
- Add Step Functions for orchestration
- Add CI/CD with GitHub Actions
- Add custom domain with Route 53 and CloudFront
- Add support for DOCX files
- Add document search with OpenSearch or Bedrock Knowledge Bases
- Add cost dashboard
- Add pre-signed POST uploads with S3-side size enforcement
- Expand automated test coverage and CI

---

## 21. Final Success Criteria

The project is complete when:

- [ ] A user can request an upload URL
- [ ] A user can upload a PDF to S3
- [ ] Upload automatically triggers processing
- [ ] Invalid or oversized uploads are rejected
- [ ] Duplicate S3 events do not overwrite completed results
- [ ] Textract extracts document text
- [ ] Bedrock returns structured analysis
- [ ] DynamoDB stores document status and result
- [ ] API Gateway returns the result
- [ ] CloudWatch contains useful logs
- [ ] IAM permissions are least-privilege
- [ ] Infrastructure is deployed with Terraform
- [ ] README is clear and professional
- [ ] Architecture diagram is included
- [ ] Project is added to CV and portfolio
