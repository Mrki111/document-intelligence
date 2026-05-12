# Architecture

```mermaid
flowchart TD
    Client[Client / curl / Postman]
    APIGW[API Gateway HTTP API]
    GenURL[Lambda: generate_upload_url]
    GetDoc[Lambda: get_document]
    Health[Lambda: health]
    S3[(S3 uploads bucket)]
    ProcDoc[Lambda: process_document]
    Textract[Amazon Textract]
    Bedrock[Amazon Bedrock]
    DDB[(DynamoDB documents table)]
    CW[CloudWatch Logs]

    Client -- POST /upload-url --> APIGW
    Client -- GET /documents/{id} --> APIGW
    Client -- GET /health --> APIGW

    APIGW --> GenURL
    APIGW --> GetDoc
    APIGW --> Health

    GenURL -->|PutItem UPLOADED| DDB
    GenURL -->|presigned URL| Client
    Client -- PUT PDF --> S3

    S3 -- ObjectCreated event --> ProcDoc
    ProcDoc -->|head_object| S3
    ProcDoc -->|DetectDocumentText| Textract
    ProcDoc -->|InvokeModel optional| Bedrock
    ProcDoc -->|UpdateItem status/result| DDB

    GetDoc -->|GetItem| DDB

    GenURL --> CW
    ProcDoc --> CW
    GetDoc --> CW
    Health --> CW
```

## Status flow

```mermaid
stateDiagram-v2
    [*] --> UPLOADED: generate_upload_url
    UPLOADED --> PROCESSING: S3 event accepted
    PROCESSING --> COMPLETED: Textract (and optional Bedrock) succeed
    PROCESSING --> FAILED: validation or processing error
    PROCESSING --> PROCESSING: stale record retried
    FAILED --> PROCESSING: retried by new S3 event
    COMPLETED --> [*]: duplicate events ignored
```
