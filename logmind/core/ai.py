import logging
from typing import List

from litellm import completion, embedding
from rich.console import Console

from logmind.config import EMBEDDING_MODEL, LLM_MODEL

console = Console()


class AIClient:
    """
    Handles interactions with the AI models via LiteLLM.
    """

    @staticmethod
    def get_embedding(text: str) -> List[float]:
        """
        Generates a vector embedding for the given text.
        """
        try:
            response = embedding(model=EMBEDDING_MODEL, input=[text])
            # Type ignore because litellm response dict is dynamic
            return response["data"][0]["embedding"]  # type: ignore
        except Exception as e:
            console.print(f"[bold red]Error generating embedding:[/bold red] {e}")
            raise

    @staticmethod
    def generate_response(prompt: str, context: str) -> str:
        """
        Generates a natural language response based on the query and context.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert IT Log Analyst. "
                    "Analyze the provided log context to answer the user's question. "
                    "Focus on root causes, anomalies, and correlations. "
                    "If the logs don't contain the answer, say so clearly."
                ),
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {prompt}",
            },
        ]

        try:
            response = completion(model=LLM_MODEL, messages=messages)
            return response["choices"][0]["message"]["content"]  # type: ignore
        except Exception as e:
            console.print(f"[bold red]Error generating response:[/bold red] {e}")
            return "Failed to generate analysis."
