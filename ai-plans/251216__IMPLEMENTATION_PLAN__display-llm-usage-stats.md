---
filename: "ai-plans/251216__IMPLEMENTATION_PLAN__display-llm-usage-stats.md"
title: "Display LLM Model Usage and Cost Statistics"
createdAt: 2025-12-16 18:15
updatedAt: 2025-12-16 18:15
status: draft
priority: medium
tags: [feature, ai, ux, litellm]
estimatedComplexity: simple
documentType: IMPLEMENTATION_PLAN
---

## Problem Description
The user wants to see information about the LLM model used for analysis and the associated cost in the `logmind analyze` command output. Currently, only the analysis text is displayed. `litellm` provides utilities to calculate costs based on token usage, which should be exposed to the user.

## Solution Overview
1.  **AI Core Update**: Modify `AIClient.generate_response` to calculate the cost of the completion using `litellm.completion_cost` and return a structured response containing the analysis text, the specific model used, and the calculated cost.
2.  **CLI Update**: Update the `analyze` command to render this metadata (Model Name, Cost) in the user interface, likely as a footer to the analysis panel or a status line.

---

## Phase 1: Update AI Client to Capture Usage

**Objective**: Enhance `AIClient` to calculate costs and return usage metadata.

### [MODIFY] logmind/core/ai.py

```python
import os
from typing import Any, Dict, List, Optional

import litellm
from litellm import completion, embedding, completion_cost
from rich.console import Console

from logmind.config import EMBEDDING_MODEL, LLM_MODEL, MAX_EMBEDDING_INPUT_CHARS

console = Console()


class AIClient:
    """
    Handles interactions with the AI models via LiteLLM.
    """

    @staticmethod
    def get_embedding(text: str) -> Optional[List[float]]:
        # ... (existing implementation remains unchanged) ...
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
    def generate_response(prompt: str, context: str) -> Dict[str, Any]:
        """
        Generates a natural language response based on the query and context.
        Returns a dictionary with 'content', 'model', and 'cost'.
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
            
            content = response["choices"][0]["message"]["content"] # type: ignore
            model_used = response.get("model", LLM_MODEL) # type: ignore
            
            # Calculate cost
            try:
                cost = completion_cost(completion_response=response)
            except Exception:
                cost = 0.0

            return {
                "content": content,
                "model": model_used,
                "cost": cost,
            }

        except Exception as e:
            console.print(f"[bold red]Error generating response:[/bold red] {e}")
            return {
                "content": "Failed to generate analysis.",
                "model": LLM_MODEL,
                "cost": 0.0,
            }
```

---

## Phase 2: Update Analysis Command Output

**Objective**: Display the gathered metadata in the CLI.

### [MODIFY] logmind/commands/analyze_cmd.py

```python
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from logmind.core.ai import AIClient
from logmind.core.db import VectorStore

app = typer.Typer()
console = Console()


@app.command("analyze")
def analyze(
    query: Annotated[
        str, typer.Argument(help="Natural language query to ask about the logs")
    ],
    limit: Annotated[
        int, typer.Option(help="Number of log chunks to retrieve as context")
    ] = 5,
) -> None:
    """
    Analyze logs using AI based on a natural language query.
    """
    console.print(f"[bold blue]Querying:[/bold blue] {query}")

    try:
        ai = AIClient()
        db = VectorStore()

        # 1. Vector Search
        query_vector = ai.get_embedding(query)
        # Handle case where embedding fails (returns None)
        if query_vector is None:
             console.print("[bold red]Failed to generate query embedding.[/bold red]")
             raise typer.Exit(code=1)

        results = db.search(query_vector, limit=limit)

        if not results:
            console.print("[yellow]No relevant logs found.[/yellow]")
            return

        # 2. Construct Context
        context_str = "\n---\n".join(
            [
                f"[Source: {r['source']} Line: {r['line_start']}]\n{r['content']}"
                for r in results
            ]
        )

        console.print(
            Panel(
                context_str,
                title="Retrieved Log Context",
                expand=False,
                border_style="dim",
            )
        )

        # 3. AI Analysis
        with console.status("[bold green]Thinking...[/bold green]"):
            result = ai.generate_response(query, context_str)

        content = result["content"]
        model = result["model"]
        cost = result["cost"]

        # Create subtitle with stats
        subtitle = Text(f"Model: {model} | Cost: ${cost:.6f}", style="dim italic")

        console.print(
            Panel(
                Markdown(content), 
                title="AI Analysis", 
                subtitle=subtitle,
                subtitle_align="right",
                border_style="green"
            )
        )

    except Exception as e:
        console.print(f"[bold red]Analysis failed:[/bold red] {e}")
        raise typer.Exit(code=1)
```

---

## Phase 3: Implementation Report

### [NEW FILE] ai-plans/251216__IMPLEMENTATION_REPORT__display-llm-usage-stats.md

```yaml
---
filename: "ai-plans/251216__IMPLEMENTATION_REPORT__display-llm-usage-stats.md"
title: "Report: Display LLM Model Usage and Cost Statistics"
createdAt: 2025-12-16 18:25
updatedAt: 2025-12-16 18:25
planFile: "ai-plans/251216__IMPLEMENTATION_PLAN__display-llm-usage-stats.md"
project: "logmind"
status: completed
filesCreated: 0
filesModified: 2
filesDeleted: 0
tags: [feature, ai, ux]
documentType: IMPLEMENTATION_REPORT
---

## Summary
Updated the `AIClient` to capture model usage and calculate costs using `litellm`'s built-in utilities. The `analyze` command was updated to handle the new structured response and display the model name and estimated cost as a subtitle in the analysis panel.

## Files Changed
- **Modified `logmind/core/ai.py`**: 
    - Updated `generate_response` to return a dictionary containing `content`, `model`, and `cost`.
    - Integrated `litellm.completion_cost`.
- **Modified `logmind/commands/analyze_cmd.py`**: 
    - Updated to handle the dictionary response from `generate_response`.
    - Added a safety check for `None` return from `get_embedding`.
    - Formatted the final `Panel` output to include a right-aligned subtitle with model and cost info.

## Key Changes
- **Cost Calculation**: Now leveraging `litellm` to automatically calculate costs based on the model and token usage.
- **UI Enhancement**: The analysis output now clearly shows which model processed the request and how much it cost (e.g., `Model: gpt-4o | Cost: $0.001234`).

## Testing Notes
- Run `logmind analyze "your query"`.
- Verify that the "AI Analysis" panel now has a footer/subtitle in the bottom right corner displaying the model name and cost.

