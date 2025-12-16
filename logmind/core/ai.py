import os
from typing import List, Optional

import litellm
from litellm import completion, embedding
from rich.console import Console

from logmind.config import EMBEDDING_MODEL, LLM_MODEL, MAX_EMBEDDING_INPUT_CHARS

console = Console()


class AIClient:
    """
    Handles interactions with the AI models via LiteLLM.
    """

    @staticmethod
    def get_embedding(text: str) -> Optional[List[float]]:
        """
        Generates a vector embedding for the given text.
        """
        if not text or not text.strip():
            return None

        if len(text) > MAX_EMBEDDING_INPUT_CHARS:
            console.print(
                f"[dim yellow]Warning: Log entry too long ({len(text)} chars). "
                f"Truncating to {MAX_EMBEDDING_INPUT_CHARS} chars.[/dim yellow]"
            )
            text = text[:MAX_EMBEDDING_INPUT_CHARS]

        try:
            return AIClient._call_embedding_api(text)
        except litellm.ContextWindowExceededError:
            console.print("[red]Token limit exceeded. Retrying with aggressive truncation...[/red]")
            try:
                shorter_text = text[: int(MAX_EMBEDDING_INPUT_CHARS / 2)]
                return AIClient._call_embedding_api(shorter_text)
            except Exception as e:
                console.print(
                    f"[bold red]Failed to embed log entry even after truncation:[/bold red] {e}"
                )
                return None
        except Exception as e:
            console.print(f"[bold red]Error generating embedding:[/bold red] {e}")
            return None

    @staticmethod
    def _call_embedding_api(text: str) -> List[float]:
        """Helper to make the actual API call."""
        api_key = os.getenv("OPENAI_API_KEY")
        kwargs = {"api_key": api_key} if api_key else {}
        response = embedding(model=EMBEDDING_MODEL, input=[text], **kwargs)
        return response["data"][0]["embedding"]  # type: ignore

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
            api_key = os.getenv("OPENAI_API_KEY")
            kwargs = {"api_key": api_key} if api_key else {}
            response = completion(model=LLM_MODEL, messages=messages, **kwargs)
            return response["choices"][0]["message"]["content"]  # type: ignore
        except Exception as e:
            console.print(f"[bold red]Error generating response:[/bold red] {e}")
            return "Failed to generate analysis."
