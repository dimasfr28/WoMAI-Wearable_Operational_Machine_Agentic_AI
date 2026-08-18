"""Unit tests for app.rag.judge.evaluate_faithfulness (RAGAS LLM-as-judge).

No real network/LLM call is made — genai.Client, llm_factory, and Faithfulness
are all mocked at the app.rag.judge import site.
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.judge import evaluate_faithfulness


class EvaluateFaithfulnessTestCase(unittest.TestCase):
    @patch("app.rag.judge.Faithfulness")
    @patch("app.rag.judge.llm_factory")
    @patch("app.rag.judge.genai")
    def test_returns_score_from_ragas(self, mock_genai, mock_llm_factory, mock_faithfulness_cls):
        mock_result = MagicMock()
        mock_result.value = 0.85
        mock_scorer = MagicMock()
        mock_scorer.ascore = AsyncMock(return_value=mock_result)
        mock_faithfulness_cls.return_value = mock_scorer

        score = evaluate_faithfulness(
            query="Why did the machine fail?",
            answer="The spindle bearing overheated (Haas Service Manual).",
            contexts=["The spindle bearing overheating causes failure per the manual."],
        )

        self.assertEqual(score, 0.85)
        mock_scorer.ascore.assert_awaited_once_with(
            user_input="Why did the machine fail?",
            response="The spindle bearing overheated (Haas Service Manual).",
            retrieved_contexts=["The spindle bearing overheating causes failure per the manual."],
        )

    @patch("app.rag.judge.Faithfulness")
    @patch("app.rag.judge.llm_factory")
    @patch("app.rag.judge.genai")
    def test_returns_none_when_ragas_raises(self, mock_genai, mock_llm_factory, mock_faithfulness_cls):
        mock_llm_factory.side_effect = RuntimeError("judge LLM unavailable")

        score = evaluate_faithfulness(query="q", answer="a", contexts=["c"])

        self.assertIsNone(score)


if __name__ == "__main__":
    unittest.main()
