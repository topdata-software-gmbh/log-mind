# Implementation Plan: LogMind - AI-Assisted Log Analyzer

## Problem Description

The goal is to build **LogMind**, a minimalistic yet powerful CLI tool for analyzing IT logs. Traditional log analysis is manual and reactive. LogMind aims to solve this by applying the **RAG (Retrieval-Augmented Generation)** pattern to log files.

The specific challenges being addressed are:
1.  **Ingestion**: Reading raw log files and storing them in a vector format that captures semantic meaning.
2.  **Context Retrieval**: Using vector similarity search (Qdrant) to find relevant log segments based on natural language queries.
3.  **AI Analysis**: Using LLMs (via LiteLLM) to interpret technical logs and explain root causes, anomalies, or correlations to the user.

## Architecture & Principles
This implementation follows **SOLID** principles:
- **SRP**: Separate modules for Database, AI, Parsing, and CLI commands.
- **OCP**: The system is designed to accept different models via configuration without changing code.
- **DIP**: High-level commands depend on abstractions (classes) of the DB and AI, not raw API calls.

---

## Phase 1: Project Initialization & Configuration

**Objective**: Set up the project structure, dependency management using `uv`, and configuration handling.

### Step 1.1: Directory Structure & Dependencies
Create the project skeleton and define dependencies in `pyproject.toml`.

```bash
mkdir -p logmind/{core,utils,commands}
touch logmind/__init__.py logmind/core/__init__.py logmind/utils/__init__.py logmind/commands/__init__.py
```

**File**: `pyproject.toml`
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "logmind"
version = "0.1.0"
description = "AI-assisted log analyzer using LiteLLM and Qdrant"
requires-python = ">=3.12"
license = "MIT"
authors = [
    { name = "Developer", email = "dev@example.com" },
]
dependencies = [
    "typer[all]>=0.9.0",
    "rich>=13.7.0",
    "litellm>=1.0.0",
    "qdrant-client>=1.7.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.0.0",
]

[project.scripts]
logmind = "logmind.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "black>=24.0.0",
    "ruff>=0.3.0",
    "mypy>=1.8.0",
]

[tool.ruff]
line-length = 88
select = ["E", "F", "W", "I"]

[tool.black]
line-length = 88
```

### Step 1.2: Environment Configuration
Define the configuration logic and environment variables.

**File**: `.env.example`
```ini
# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333

# AI Configuration (LiteLLM supports OpenAI, Anthropic, Ollama, etc.)
# Example for OpenAI
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
```

**File**: `logmind/config.py`
```python
import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Application Settings
APP_NAME = "LogMind"
ROOT_DIR = Path(__file__).parent.parent

# Qdrant Settings
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "logs_collection"
VECTOR_SIZE = 1536  # Adjust based on your embedding model

# AI Settings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")

# CLI Settings
CLI_CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
}
```

---

## Phase 2: Core Infrastructure (AI & Database)

**Objective**: Implement the interfaces for `litellm` and `qdrant-client`.

### Step 2.1: Qdrant Vector Store
Create a wrapper around Qdrant to handle collection management and vector upserts.

**File**: `logmind/core/db.py`
```python
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from logmind.config import (
    COLLECTION_NAME,
    QDRANT_HOST,
    QDRANT_PORT,
    VECTOR_SIZE,
)


class VectorStore:
    """
    Manages interactions with the Qdrant vector database.
    """

    def __init__(self) -> None:
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Creates the collection if it does not exist."""
        if not self.client.collection_exists(COLLECTION_NAME):
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=VECTOR_SIZE, distance=models.Distance.COSINE
                ),
            )

    def upsert_logs(
        self, logs: List[Dict[str, Any]], vectors: List[List[float]]
    ) -> None:
        """
        Stores log entries and their vectors in Qdrant.
        """
        points = [
            models.PointStruct(
                id=self._generate_id(idx),
                vector=vector,
                payload=log,
            )
            for idx, (log, vector) in enumerate(zip(logs, vectors))
        ]

        # In a real scenario, use batching for large lists
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    def search(self, vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches for the most relevant logs based on the query vector.
        """
        results = self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            limit=limit,
        )
        return [hit.payload for hit in results if hit.payload]

    def _generate_id(self, offset: int) -> int:
        """
        Helper to generate an ID.
        Note: In production, UUIDs are preferred over count-based IDs to avoid collisions.
        """
        info = self.client.get_collection(COLLECTION_NAME)
        return info.points_count + offset + 1
```

### Step 2.2: AI Client (LiteLLM)
Create a wrapper for LiteLLM to handle embeddings and chat completion.

**File**: `logmind/core/ai.py`
```python
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
```

---

## Phase 3: Data Parsing & Ingestion Command

**Objective**: Create the logic to read files, chunk them, and feed them into the `VectorStore`.

### Step 3.1: Log Parser Utility
**File**: `logmind/utils/parser.py`
```python
from pathlib import Path
from typing import Dict, List


def parse_log_file(file_path: Path, chunk_size: int = 15) -> List[Dict[str, str]]:
    """
    Reads a log file and groups lines into chunks to maintain context.
    
    Args:
        file_path: Path to the log file.
        chunk_size: Number of lines per chunk.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")

    chunks = []
    for i in range(0, len(lines), chunk_size):
        chunk_content = "".join(lines[i : i + chunk_size])
        chunks.append({
            "content": chunk_content,
            "source": str(file_path.name),
            "line_start": str(i + 1),
        })
    
    return chunks
```

### Step 3.2: Ingest Command
**File**: `logmind/commands/ingest_cmd.py`
```python
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import track

from logmind.core.ai import AIClient
from logmind.core.db import VectorStore
from logmind.utils.parser import parse_log_file

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
            help="Path to the log file to ingest",
        ),
    ],
) -> None:
    """
    Ingest a log file into the vector database.
    """
    console.print(f"[bold blue]Processing file:[/bold blue] {file_path}")

    # 1. Parse Logs
    try:
        chunks = parse_log_file(file_path)
    except Exception as e:
        console.print(f"[bold red]Failed to parse file:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"Found {len(chunks)} log chunks.")

    # 2. Initialize Core Systems
    ai = AIClient()
    db = VectorStore()

    # 3. Embed and Store
    vectors = []
    logs_to_store = []

    try:
        for chunk in track(chunks, description="Generating embeddings..."):
            vector = ai.get_embedding(chunk["content"])
            vectors.append(vector)
            logs_to_store.append(chunk)

        console.print("[yellow]Storing in Qdrant...[/yellow]")
        db.upsert_logs(logs_to_store, vectors)
        console.print("[bold green]Ingestion complete![/bold green]")

    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        raise typer.Exit(code=1)
```

---

## Phase 4: Analysis Command

**Objective**: Implement the RAG pipeline command.

**File**: `logmind/commands/analyze_cmd.py`
```python
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

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
            answer = ai.generate_response(query, context_str)

        console.print(
            Panel(Markdown(answer), title="AI Analysis", border_style="green")
        )

    except Exception as e:
        console.print(f"[bold red]Analysis failed:[/bold red] {e}")
        raise typer.Exit(code=1)
```

---

## Phase 5: CLI Entry Point & User Documentation

**Objective**: Connect the commands to the main CLI application and document usage.

### Step 5.1: Main Entry Point
**File**: `logmind/cli.py`
```python
import typer

from logmind.commands import analyze_cmd, ingest_cmd
from logmind.config import CLI_CONTEXT_SETTINGS

app = typer.Typer(
    context_settings=CLI_CONTEXT_SETTINGS,
    help="LogMind: AI-Assisted Log Analysis Tool",
    no_args_is_help=True,
)

app.add_typer(ingest_cmd.app)
app.add_typer(analyze_cmd.app)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

### Step 5.2: User Documentation

**File**: `README.md`

```markdown
# LogMind

LogMind is a minimalistic AI-assisted log analysis tool. It ingests log files into a local Qdrant vector database and uses LLMs (via LiteLLM) to perform root cause analysis and explain anomalies.

## Prerequisites

1.  **Python**: 3.12+
2.  **uv**: Installed via `curl -LsSf https://astral.sh/uv/install.sh | sh`
3.  **Qdrant**: Running locally.
    ```bash
    docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant
    ```

## Installation

1.  **Setup Environment**:
    ```bash
    # Create virtual environment and install dependencies
    uv venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
    ```

2.  **Configuration**:
    Copy `.env.example` to `.env` and add your API keys.
    ```bash
    cp .env.example .env
    # Edit .env with your OpenAI/Anthropic/Ollama keys
    ```

## Usage

### 1. Ingest Logs
Read a log file, chunk it, generate embeddings, and store it in Qdrant.

```bash
logmind ingest /path/to/server.log
```

### 2. Analyze Logs
Ask questions in natural language. LogMind retrieves relevant log chunks and generates an AI analysis.

```bash
logmind analyze "Why did the database connection fail around 8 AM?"
```

## Development

- **Format Code**: `uv run ruff format .`
- **Lint Code**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`







