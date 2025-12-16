---
filename: "ai-plans/251216__IMPLEMENTATION_PLAN__fix-context-window-exceeded.md"
title: "Fix Context Window Exceeded Error in Ingestion"
createdAt: 2025-12-16 13:15
updatedAt: 2025-12-16 13:15
status: draft
priority: critical
tags: [bugfix, ai, ingestion, stability]
estimatedComplexity: moderate
documentType: IMPLEMENTATION_PLAN
---

## Problem Description
The user is encountering a `litellm.ContextWindowExceededError` during the ingestion of a large CSV file.
Specific details:
- **Model Limit:** 8,192 tokens (`text-embedding-3-small`).
- **Input Size:** 42,112 tokens (a massive log entry, likely containing a full stack trace or response body).
- **Result:** The application crashes, halting the entire ingestion process.

Current behavior sends the raw text content directly to the embedding model without size checks.

## Solution Overview
We need to implement a "Safe Embedding" mechanism that prevents crashes when log entries are too large.

1.  **Configuration**: Define a `MAX_EMBEDDING_INPUT_CHARS` constant. Since 1 token $\approx$ 4 characters, a safe limit for 8k tokens is roughly 32,000 characters. We will be conservative and set it to 24,000.
2.  **AI Client Resilience**: Update `AIClient.get_embedding`:
    - Truncate input text *before* the API call if it exceeds the character limit.
    - Implement a `try/except` block specifically for `ContextWindowExceededError`.
    - If the API still rejects it (token density varies), perform a "hard truncate" (cut length in half) and retry once.
    - Return `None` if it fails ultimately, allowing the caller to skip the record instead of crashing.
3.  **Ingestion Flow**: Update `ingest_cmd.py` to handle cases where embedding generation returns `None` (skip the record).

## Architecture & Principles
-   **SRP**: The `AIClient` is responsible for adapting data to the constraints of the LLM provider.
-   **Resilience**: The system should degrade gracefully (skipping one bad log) rather than crashing the whole batch.

---

## Phase 1: Configuration

**Objective**: Define safety limits for inputs.

### [MODIFY] logmind/config.py

```python
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent

# Load environment variables
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# Application Settings
APP_NAME = "LogMind"

# Qdrant Settings
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "logs_collection"
VECTOR_SIZE = 1536  # Adjust based on your embedding model

# AI Settings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

# Safety Limits
# approx 1 token = 4 chars. 8192 tokens ~= 32k chars. 
# We set a conservative limit to leave room for overhead.
MAX_EMBEDDING_INPUT_CHARS = 24000 

# CLI Settings
CLI_CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
}
```

---

## Phase 2: Resilient AI Client

**Objective**: Update `AIClient` to handle oversized inputs and return `None` on failure instead of raising.

### [MODIFY] logmind/core/ai.py

```python
import logging
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
        Returns None if embedding fails or text is invalid.
        """
        if not text or not text.strip():
            return None

        # 1. Pre-emptive Truncation (Character based)
        if len(text) > MAX_EMBEDDING_INPUT_CHARS:
            console.print(
                f"[dim yellow]Warning: Log entry too long ({len(text)} chars). "
                f"Truncating to {MAX_EMBEDDING_INPUT_CHARS} chars.[/dim yellow]"
            )
            text = text[:MAX_EMBEDDING_INPUT_CHARS]

        try:
            return AIClient._call_embedding_api(text)
        except litellm.ContextWindowExceededError:
            # 2. Reactive Truncation (if token count still too high)
            console.print("[red]Token limit exceeded. Retrying with aggressive truncation...[/red]")
            try:
                # Cut in half again to be safe
                shorter_text = text[: int(MAX_EMBEDDING_INPUT_CHARS / 2)]
                return AIClient._call_embedding_api(shorter_text)
            except Exception as e:
                console.print(f"[bold red]Failed to embed log entry even after truncation:[/bold red] {e}")
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
        # Type ignore because litellm response dict is dynamic
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
```

---

## Phase 3: Update Ingestion Logic

**Objective**: Modify `ingest_cmd` to skip records where embedding returned `None`.

### [MODIFY] logmind/commands/ingest_cmd.py

```python
from pathlib import Path
from typing import Annotated

import os
import typer
from rich.console import Console
from rich.progress import track

from logmind.core.ai import AIClient
from logmind.core.db import VectorStore
from logmind.utils.parser import load_file

app = typer.Typer()
console = Console()


@app.command("ingest")
def ingest(
    file_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to the log file (supports .log, .txt, .csv, .json)",
        ),
    ],
) -> None:
    """
    Ingest a log file into the vector database.
    """
    console.print(f"[bold blue]Processing file:[/bold blue] {file_path}")

    if not os.getenv("OPENAI_API_KEY"):
        console.print(
            "[bold yellow]OPENAI_API_KEY is not set for this process.[/bold yellow] "
            "If you're running via sudo, your shell env may not be preserved. "
            "Try `sudo -E ...` or put the key into the project's `.env` file."
        )

    # 1. Parse Logs
    try:
        chunks = load_file(file_path)
    except Exception as e:
        console.print(f"[bold red]Failed to parse file:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"Found {len(chunks)} log entries.")

    # 2. Initialize Core Systems
    ai = AIClient()
    db = VectorStore()

    # 3. Embed and Store
    vectors = []
    logs_to_store = []
    skipped_count = 0

    try:
        for chunk in track(chunks, description="Generating embeddings..."):
            vector = ai.get_embedding(chunk["content"])
            
            if vector is None:
                skipped_count += 1
                continue

            vectors.append(vector)
            logs_to_store.append(chunk)

        if skipped_count > 0:
            console.print(f"[yellow]Skipped {skipped_count} entries due to embedding errors/size limits.[/yellow]")

        if logs_to_store:
            console.print(f"[yellow]Storing {len(logs_to_store)} entries in Qdrant...[/yellow]")
            db.upsert_logs(logs_to_store, vectors)
            console.print("[bold green]Ingestion complete![/bold green]")
        else:
            console.print("[bold red]No valid logs to store.[/bold red]")

    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        raise typer.Exit(code=1)
```

---

## Phase 4: Implementation Report

**Objective**: Document the changes.

### [NEW FILE] ai-plans/251216__IMPLEMENTATION_REPORT__fix-context-window-exceeded.md

```yaml
---
filename: "ai-plans/251216__IMPLEMENTATION_REPORT__fix-context-window-exceeded.md"
title: "Report: Fix Context Window Exceeded Error in Ingestion"
createdAt: 2025-12-16 13:25
updatedAt: 2025-12-16 13:25
planFile: "ai-plans/251216__IMPLEMENTATION_PLAN__fix-context-window-exceeded.md"
project: "logmind"
status: completed
filesCreated: 0
filesModified: 3
filesDeleted: 0
tags: [bugfix, ai, stability]
documentType: IMPLEMENTATION_REPORT
---

## Summary
Fixed the critical crash during ingestion of large files caused by `ContextWindowExceededError`. The system now safeguards against oversized log entries by truncating them and skipping entries that cannot be processed, ensuring the ingestion pipeline completes successfully.

## Files Changed
- **Modified `logmind/config.py`**: Added `MAX_EMBEDDING_INPUT_CHARS` constant (24,000).
- **Modified `logmind/core/ai.py`**:
    - `get_embedding` now returns `Optional[List[float]]`.
    - Added pre-emptive character truncation.
    - Added `try/except` for `ContextWindowExceededError` with a retry mechanism using aggressive truncation.
- **Modified `logmind/commands/ingest_cmd.py`**:
    - Updated loop to handle `None` returns from embedding generation.
    - Added counters and user feedback for skipped entries.

## Key Changes
- **Pre-emptive Truncation**: Inputs > 24,000 chars are truncated before hitting the API.
- **Error Handling**: Specific handling for LiteLLM context errors prevents the whole process from dying.
- **Data Integrity**: Using `zip` implicitly via separate lists was replaced by a logic where `vectors` and `logs_to_store` are only appended to if the vector generation succeeds.

## Testing Notes
- Run ingestion on the large CSV file: `logmind ingest shopware6-api-error-logs__2025-12-16_1151.csv`.
- Observe that the progress bar continues even if warnings about "Log entry too long" appear.
- Verify that the final success message reports the number of skipped entries.
```

