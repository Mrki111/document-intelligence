# Captured Evidence

Start with [`../journey.md`](../journey.md) — it explains what each file in this directory proves about the design.

These files are **sanitized captures from a real AWS run.** Account-specific identifiers have been replaced with placeholders:

| Placeholder | Original |
|---|---|
| `<aws-account-id>` | 12-digit AWS account ID |
| `<api-id>` | API Gateway HTTP API ID (subdomain in `…execute-api.us-east-1.amazonaws.com`) |
| `<bucket-name>` | S3 bucket name (contains the account ID) |
| `<presigned-url-redacted>` | Full presigned S3 PUT URL (expired, but kept off the repo) |
| `<receipt-handle-redacted>` | SQS message receipt handle |
| `<signature-redacted>`, `<signing-cert-url-redacted>`, `<unsubscribe-url-redacted>` | SNS message envelope fields |
| `<subscription-arn-redacted>`, `<topic-arn-redacted>` | SNS subscription / topic ARNs (preserved structure, account ID redacted) |
| `<sender-id-redacted>`, `<trace-header-redacted>` | SQS message-attribute fields |

The deployed stack has been torn down (`terraform destroy`) — the placeholders aren't load-bearing; they're hygiene.

## File map (quick reference)

| File | Scenario |
|---|---|
| `01_upload_url_request.json` – `03_get_document_completed.json` | Happy path: upload → poll → COMPLETED |
| `04_invalid_request.json` – `05_invalid_response.json` | Pre-signature validation gate (HTTP 400) |
| `06_mismatched_size_request.json` – `07_mismatched_size_final.json` | Post-upload HEAD revalidation (FAILED with INVALID_UPLOAD_SIZE) |
| `dynamo_doc_*.json` | DynamoDB records for the two persisted documents |
| `logs_*.txt` | CloudWatch log tails: process_document, complete_document_processing, DLQ retry sequence |
| `dlq_message.json`, `dlq_depth.json`, `dlq_alarm_state.json` | DLQ + alarm evidence from a forced failure |
| `terraform_plan_summary.txt`, `terraform_apply.txt`, `terraform_outputs.txt` | Provisioning evidence |
| `screenshots/*.png` | Console screenshots supporting the DynamoDB, SQS DLQ, and CloudWatch alarm evidence |
