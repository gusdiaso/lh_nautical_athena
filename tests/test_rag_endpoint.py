import json
import unittest
from unittest.mock import MagicMock

from src.analytics_ai.rag_documents import Chunk
from src.analytics_ai.rag_endpoint import RateLimitedChatClient, RateLimitRetriesExhausted
from src.analytics_ai.rag_generation import generate_answer
from src.analytics_ai.rag_groundedness import evaluate_groundedness


class HttpError(RuntimeError):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def _response(content):
    result = MagicMock()
    result.choices[0].message.content = content
    return result


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class RagEndpointTest(unittest.TestCase):
    def _client(self, underlying, fake, interval=0):
        return RateLimitedChatClient(
            underlying, interval, sleep=fake.sleep, clock=fake.clock, jitter=lambda: 0.0
        )

    def test_429_then_success_retries_with_backoff(self):
        underlying = MagicMock()
        underlying.create.side_effect = [HttpError(429, "limited"), "ok"]
        fake = FakeTime()

        result = self._client(underlying, fake).create(model="m")

        self.assertEqual(result, "ok")
        self.assertEqual(underlying.create.call_count, 2)
        self.assertEqual(fake.sleeps, [2.0])

    def test_429_exhaustion_reports_original_error_and_attempts(self):
        underlying = MagicMock()
        underlying.create.side_effect = HttpError(429, "REQUEST_LIMIT_EXCEEDED")
        fake = FakeTime()

        with self.assertRaisesRegex(
            RateLimitRetriesExhausted, "after 4 attempts: REQUEST_LIMIT_EXCEEDED"
        ):
            self._client(underlying, fake).create(model="m")

        self.assertEqual(underlying.create.call_count, 4)
        self.assertEqual(fake.sleeps, [2.0, 4.0, 8.0])

    def test_non_429_is_not_retried(self):
        underlying = MagicMock()
        underlying.create.side_effect = HttpError(401, "unauthorized")
        fake = FakeTime()

        with self.assertRaisesRegex(HttpError, "unauthorized"):
            self._client(underlying, fake).create(model="m")

        underlying.create.assert_called_once()
        self.assertEqual(fake.sleeps, [])

    def test_configured_interval_is_respected_between_calls(self):
        underlying = MagicMock()
        underlying.create.side_effect = ["one", "two"]
        fake = FakeTime()
        client = self._client(underlying, fake, interval=2.0)

        client.create(model="m")
        client.create(model="m")

        self.assertEqual(fake.sleeps, [2.0])

    def test_generation_and_judge_share_the_same_rate_limited_client(self):
        underlying = MagicMock()
        judge_json = json.dumps({
            "claims": [{"claim_id": "claim_1", "verdict": "supported",
                        "evidence_ids": ["evidence_1"]}],
        })
        underlying.create.side_effect = [_response("Resposta documental."), _response(judge_json)]
        fake = FakeTime()
        client = self._client(underlying, fake, interval=2.0)
        chunk = Chunk(
            "id", "docs/staging.md", "staging.md", "markdown", "Objetivo",
            "Resposta documental.", "hash", "date", "approved",
        )

        generated = generate_answer(client, "Pergunta?", [chunk], "model")
        judged = evaluate_groundedness(
            client, "Pergunta?", generated.answer, [chunk], [], "model"
        )

        self.assertEqual(underlying.create.call_count, 2)
        self.assertEqual(fake.sleeps, [2.0])
        self.assertEqual(judged.status, "completed")

    def test_exhausted_judge_rate_limit_is_endpoint_error_with_attempt_count(self):
        underlying = MagicMock()
        underlying.create.side_effect = HttpError(429, "REQUEST_LIMIT_EXCEEDED")
        fake = FakeTime()
        client = self._client(underlying, fake)
        chunk = Chunk(
            "id", "docs/staging.md", "staging.md", "markdown", "Objetivo",
            "Resposta documental.", "hash", "date", "approved",
        )

        result = evaluate_groundedness(
            client, "Pergunta?", "Resposta documental.", [chunk], [], "model"
        )

        self.assertEqual(result.status, "endpoint_error")
        self.assertIn("after 4 attempts: REQUEST_LIMIT_EXCEEDED", result.failure_reason)
        self.assertIsNone(result.grounded)


if __name__ == "__main__":
    unittest.main()
