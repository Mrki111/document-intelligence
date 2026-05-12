from __future__ import annotations

import unittest

from shared.bedrock import BedrockOutputError, parse_model_json, validate_model_json


class BedrockTest(unittest.TestCase):
    def test_validates_resume_schema(self) -> None:
        payload = parse_model_json(
            """
            {
              "summary": "Cloud engineer",
              "candidateLevel": "Junior",
              "skills": ["AWS"],
              "awsServicesMentioned": ["S3"],
              "strengths": [],
              "weaknesses": [],
              "missingKeywords": [],
              "recommendedProjects": [],
              "atsScore": 75
            }
            """
        )

        validate_model_json("resume", payload)

    def test_rejects_invalid_ats_score(self) -> None:
        with self.assertRaises(BedrockOutputError):
            validate_model_json(
                "resume",
                {
                    "summary": "Cloud engineer",
                    "candidateLevel": "Junior",
                    "skills": ["AWS"],
                    "awsServicesMentioned": ["S3"],
                    "strengths": [],
                    "weaknesses": [],
                    "missingKeywords": [],
                    "recommendedProjects": [],
                    "atsScore": 101,
                },
            )


if __name__ == "__main__":
    unittest.main()
