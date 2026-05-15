# Document Intelligence — Evidence Walkthrough

This document maps each artifact in [`docs/examples/`](examples/) to the design decision it verifies. Read this page first; the JSON/log files are the supporting evidence.

## TL;DR

A serverless document-intelligence pipeline that turns an uploaded PDF into structured Bedrock analysis via async Textract. The evidence below captures one end-to-end run on real AWS, two intentional failure paths, and a resilience demo (DLQ + CloudWatch alarm).

Headline numbers from this run, on a 15-page PDF (Amazon Q4 2025 Earnings Call transcript):

| Metric | Value |
|---|---|
| End-to-end upload → COMPLETED | ~25 s |
| `process_document` cold start | 129 ms |
| `process_document` hot duration | 2.07 s |
| `complete_document_processing` duration (Textract pagination + Bedrock) | 11.88 s |
| Lambda memory headroom | 98–116 MB used / 512 MB allocated |
| Resources provisioned cleanly | 55 added, 0 changed, 0 destroyed |

## Architecture

See [`architecture.md`](architecture.md). One-line summary:

`S3 upload → process_document (StartDocumentTextDetection) → SNS → complete_document_processing (GetDocumentTextDetection + optional Bedrock) → DynamoDB`.

The async Textract handoff is what makes multi-page PDFs feasible without blocking a Lambda for the full OCR duration.

## 1. Provisioning

| File | Shows |
|---|---|
| `terraform_plan_summary.txt` | `Plan: 55 to add, 0 to change, 0 to destroy` — clean deploy, no destructive ops. |
| `terraform_apply.txt` | Apply transcript ending in `Apply complete! Resources: 55 added, 0 changed, 0 destroyed`. |
| `terraform_outputs.txt` | API endpoint, DynamoDB table name, SNS topic ARN, DLQ URL. |

## 2. Happy path

The script [`scripts/demo.sh`](../scripts/demo.sh) drives:

1. `POST /upload-url` with declared filename, type, size → 201 with presigned URL + `documentId`.
2. `PUT` the PDF to the presigned URL → S3 stores it.
3. S3 ObjectCreated event → `process_document` revalidates the actual object via `HeadObject`, starts an async Textract job, writes `PROCESSING` + `textractJobId` to DynamoDB.
4. Textract publishes to SNS on completion → `complete_document_processing` paginates `GetDocumentTextDetection`, invokes Bedrock, writes `COMPLETED` + extracted preview + page count + analysis.
5. `GET /documents/{id}` returns the final record.

| File | Content |
|---|---|
| `01_upload_url_request.json` | Client POST body |
| `02_upload_url_response.json` | `documentId`, `uploadUrl`, `s3Key` |
| `03_get_document_completed.json` | Final API response with `pageCount: 15`, `extractedTextPreview`, full `analysis{}` |
| `dynamo_doc_d1b…json` | Same record from DynamoDB, including `textractJobId`, `s3ETag`, and split timestamps |
| `logs_process_document.txt` | Lambda START/REPORT with 2.07 s duration and 129 ms cold start |
| `logs_complete_document_processing.txt` | 11.88 s duration; the bulk is Textract pagination + Bedrock |

### Notable evidence

**Timestamp split** — the COMPLETED DynamoDB record has:
- `textractJobStartedAt: 2026-05-15T08:24:48Z`
- `updatedAt:            2026-05-15T08:25:00Z`

12 seconds apart. The two come from distinct `clock()` calls — one immediately after the Textract API returned, one when the completion handler wrote the final record. Reusing a single function-entry `now` would have collapsed them; the gap proves the split is real.

**Bedrock schema validation** — the `analysis` object in `03_get_document_completed.json` has exactly the keys the `general` schema demands (`summary`, `title`, `keyPoints`, `risks`, `actionItems`, `entities`). The Bedrock wrapper rejects malformed model output before it reaches DynamoDB; see [`backend/shared/bedrock.py`](../backend/shared/bedrock.py).

## 3. Failure path: pre-signature validation gate

A client sends `documentType: "unknown"` to `POST /upload-url`.

| File | Content |
|---|---|
| `04_invalid_request.json` | The malformed body |
| `05_invalid_response.json` | HTTP 400, body: `"documentType must be one of: general, invoice, resume."` |

**Decision being verified:** validation must happen *before* the presigned URL is signed and *before* any DynamoDB record is created. A malformed client cannot even reserve an S3 path.

## 4. Failure path: post-upload HEAD revalidation

A client requests an upload URL with `contentLength: 999999`, then PUTs a 140 705-byte file. S3 accepts the upload (presigned PUT doesn't enforce declared size).

| File | Content |
|---|---|
| `06_mismatched_size_request.json` | Request claiming 999 999 bytes |
| `07_mismatched_size_final.json` | API response: `status: FAILED, failureReason: INVALID_UPLOAD_SIZE` |
| `dynamo_doc_c66…json` | DynamoDB record showing no `textractJobId` (the document never reached Textract) |

**Decision being verified:** the pre-signature gate is necessary but not sufficient. `process_document` re-runs the size/content-type checks against the actual S3 object before spending money on Textract. Defense in depth.

## 5. Resilience: SNS retries → DLQ → alarm

Triggered by publishing a malformed payload directly to the Textract completion SNS topic, bypassing Textract and forcing `complete_document_processing` to fail on `json.loads()`:

```bash
aws sns publish --topic-arn "$TOPIC_ARN" --message "not-a-textract-notification"
```

| File | Content |
|---|---|
| `logs_dlq_retries.txt` | Three failed invocations with same `RequestId`, spaced 1 min and 2 min apart |
| `dlq_message.json` | Original malformed payload preserved in SQS with `RequestID` + `ErrorMessage` attributes |
| `dlq_depth.json` | `ApproximateNumberOfMessages: 1` |
| `dlq_alarm_state.json` | `StateValue: ALARM` with `StateReason` quoting threshold crossing |

### Async retry pattern (from `logs_dlq_retries.txt`)

| Attempt | Time | Duration | Init? |
|---|---|---|---|
| 1 | 08:30:54 | 1365 ms | yes (120 ms cold start) |
| 2 | 08:31:50 (+1 min) | 43 ms | warm |
| 3 | 08:33:51 (+2 min) | 53 ms | warm |

All three carry the same `RequestId: 364223bc-…`. That's proof this is AWS Lambda's async retry mechanism (with exponential backoff), not three separate publishes.

### End-to-end traceability

The DLQ message attributes in `dlq_message.json` include `RequestID: 364223bc-…` — the *same* RequestId from the three failed Lambda invocations. A reviewer can trace from a queued DLQ message back to the exact CloudWatch log stream that produced it.

The DLQ message body also preserves the full original SNS envelope (`Type`, `Signature`, `Timestamp`, `TopicArn`, `MessageId`, `Message`). Forensic-grade — nothing is summarised or dropped.

### Alarm timing (from `dlq_alarm_state.json`)

- Final failure: `08:33:51`
- Alarm `StateTransitionedTimestamp`: `08:36:04`
- Latency: ~2.5 min, aligning to the next 5-min CloudWatch eval boundary.
- Configuration: `EvaluationPeriods: 1`, `Period: 300`, `TreatMissingData: notBreaching`.

### Why two DLQs

The Lambda has `dead_letter_config` *and* the SNS subscription has a `redrive_policy` — both pointing at the same SQS queue. They cover different failure modes:

- Lambda `dead_letter_config`: Lambda was invoked but failed all async retries (this run).
- SNS `redrive_policy`: SNS couldn't deliver to Lambda at all (deleted function, denied permission).

Skipping either would leave a class of failures invisible.

## Notable design decisions surfaced by this evidence

- **Idempotent S3 event handling.** Duplicate S3 events on a COMPLETED document return `IGNORED_COMPLETED`; on a PROCESSING document return `IGNORED_PROCESSING` until a stale-timestamp threshold passes. The `_mark_processing` and `_mark_textract_job_started` updates both use DynamoDB conditional expressions. See [`backend/lambdas/process_document/app.py`](../backend/lambdas/process_document/app.py).
- **Stale-job protection in the completion handler.** Before writing COMPLETED, `complete_document_processing` checks that the SNS-supplied `JobId` matches the record's stored `textractJobId`. An out-of-order or duplicate notification returns `IGNORED_STALE_JOB`.
- **Per-Lambda IAM roles.** One shared role would hide the blast radius. The completion Lambda gets `textract:GetDocumentTextDetection`, `bedrock:InvokeModel`, table-scoped DynamoDB, and DLQ-scoped `sqs:SendMessage` — and nothing else.
- **Textract-specific publish role with `iam:PassRole` condition.** The process Lambda can only pass the publish role to `textract.amazonaws.com` (`iam:PassedToService` condition). Prevents misuse if the IAM policy is ever copy-pasted.

## How to reproduce

```bash
terraform -chdir=infra apply
PDF=/path/to/your.pdf ./scripts/demo.sh
terraform -chdir=infra destroy  # tear down; docs/examples/ files survive
```
