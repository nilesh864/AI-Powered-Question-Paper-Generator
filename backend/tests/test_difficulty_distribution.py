import unittest
from collections import Counter
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.models.paper import DifficultyDistribution, PaperRequest, difficulty_counts_for
from app.services import rag_pipeline
from app.services.ollama_service import OllamaUnavailable


class DifficultyDistributionTests(unittest.TestCase):
    def test_legacy_difficulty_level_maps_to_a_single_tier(self):
        request = PaperRequest(subject="Physics", units=["Unit 1"], difficulty_level="Hard")

        self.assertEqual(request.difficulty_distribution, DifficultyDistribution(easy=0, medium=0, hard=100))
        self.assertEqual(request.difficulty_level, "Hard")

    def test_custom_distribution_requires_one_hundred_percent(self):
        with self.assertRaises(ValidationError):
            PaperRequest(
                subject="Physics",
                units=["Unit 1"],
                difficulty_distribution={"easy": 30, "medium": 40, "hard": 20},
            )

    def test_largest_remainder_counts_add_to_question_total(self):
        distribution = DifficultyDistribution(easy=30, medium=50, hard=20)

        self.assertEqual(difficulty_counts_for(10, distribution), {"easy": 3, "medium": 5, "hard": 2})
        self.assertEqual(sum(difficulty_counts_for(7, distribution).values()), 7)

    def test_offline_templates_tag_questions_by_requested_percentages(self):
        distribution = DifficultyDistribution(easy=30, medium=50, hard=20)
        questions = rag_pipeline._offline_question_set(
            "Physics",
            ["Unit 1"],
            ["Short Answer"] * 10,
            "",
            difficulty_distribution=distribution,
        )

        self.assertEqual(Counter(question["difficulty"] for question in questions), {"Easy": 3, "Medium": 5, "Hard": 2})
        self.assertTrue(all(question["generated_by"] == "offline_fallback" for question in questions))


class ProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_uses_ollama_then_templates_when_gemini_and_ollama_fail(self):
        distribution = {"easy": 30, "medium": 50, "hard": 20}
        with (
            patch.object(rag_pipeline.settings, "gemini_api_key", "configured-key"),
            patch("app.services.rag_pipeline.retrieve_context", new=AsyncMock(return_value="")),
            patch("app.services.rag_pipeline._invoke_with_model_fallback", new=AsyncMock(side_effect=RuntimeError("offline"))) as gemini,
            patch("app.services.rag_pipeline.generate_structured_output", new=AsyncMock(side_effect=OllamaUnavailable("Ollama unavailable"))) as ollama,
        ):
            questions = await rag_pipeline.generate_question_set(
                "Physics",
                ["Unit 1"],
                10,
                "A",
                "owner",
                ["Short Answer"],
                provider="auto",
                difficulty_distribution=distribution,
            )

        self.assertEqual(gemini.await_count, 1)
        self.assertEqual(ollama.await_count, 1)
        self.assertEqual(Counter(question["difficulty"] for question in questions), {"Easy": 3, "Medium": 5, "Hard": 2})
        self.assertTrue(all(question["generated_by"] == "offline_fallback" for question in questions))


if __name__ == "__main__":
    unittest.main()