from __future__ import annotations

PROMPTS = {
    "resume": """Analyze this resume for a cloud engineering or AI cloud engineering role.

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
""",
    "invoice": """Extract invoice information from this document.

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
""",
    "general": """Analyze this document.

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
""",
}


EXPECTED_SCHEMA_KEYS = {
    "resume": {
        "summary",
        "candidateLevel",
        "skills",
        "awsServicesMentioned",
        "strengths",
        "weaknesses",
        "missingKeywords",
        "recommendedProjects",
        "atsScore",
    },
    "invoice": {
        "vendorName",
        "invoiceNumber",
        "invoiceDate",
        "dueDate",
        "currency",
        "totalAmount",
        "lineItems",
        "missingFields",
    },
    "general": {
        "title",
        "summary",
        "keyPoints",
        "actionItems",
        "risks",
        "entities",
    },
}


def build_prompt(document_type: str, extracted_text: str, *, text_limit: int) -> str:
    template = PROMPTS[document_type]
    limited_text = extracted_text[:text_limit]
    return f"{template}\n\nDocument text:\n{limited_text}"
