---
filename: "ai-plans/251216__IMPLEMENTATION_PLAN__structured-ingestion-shopware.md"
title: "Add Structured Data Ingestion (CSV/JSON) for Database Logs"
createdAt: 2025-12-16 10:05
updatedAt: 2025-12-16 10:05
status: draft
priority: high
tags: [feature, parser, db, shopware]
estimatedComplexity: moderate
documentType: IMPLEMENTATION_PLAN
---

## Problem Description
The user needs to analyze **Shopware 6 API Error Logs** stored in a MySQL/MariaDB database. The current `ingest` command parses files as unstructured raw text, chunking strictly by line count. This approach destroys the semantic integrity of structured data exports (CSV/JSON), where a single "log entry" corresponds to a row, not a specific number of lines.

Additionally, the current Qdrant ID generation strategy (counting points) is unsafe for bulk ingestion of database exports, as it may lead to ID collisions if data is deleted and re-ingested.

## Solution Overview
We will implement:
1.  **Robust ID Generation**: Switch from sequential integers to UUIDs to ensure safe, idempotent ingestion.
2.  **Structured Parsers**: Add dedicated parsing logic for `.csv` and `.json` files that converts rows/objects into semantic text blocks suitable for LLM analysis.
3.  **Auto-detection**: Update the CLI to automatically select the correct parser based on file extension.

This allows the user to simply export their `shopware6_api_error_log` table to CSV from Adminer and run `logmind ingest export.csv`.

## Architecture & Principles
-   **SRP**: New parsing logic resides strictly in `utils/parser.py`.
-   **OCP**: The parser dispatcher allows adding new formats (e.g., XML) without changing the CLI command.
-   **Compatibility**: The output of all parsers normalizes to the existing dictionary structure (`content`, `source`, `line_start`) expected by the vector store.

---

## Phase 1: Harden Core Infrastructure

**Objective**: Replace the unsafe integer ID generation with UUIDs to support robust dataset updates.

### [MODIFY] logmind/core/db.py

```python
import uuid
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
                id=str(uuid.uuid4()),  # Changed: Use UUID for robust IDs
                vector=vector,
                payload=log,
            )
            for log, vector in zip(logs, vectors)
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
```

---

## Phase 2: Implement Structured Parsers

**Objective**: Create parsers that transform structured rows into semantically rich text blocks.

### [MODIFY] logmind/utils/parser.py

```python
import csv
import json
from pathlib import Path
from typing import Dict, List, Any


def parse_text_file(file_path: Path, chunk_size: int = 15) -> List[Dict[str, str]]:
    """Reads a raw log file and groups lines into chunks."""
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


def parse_csv_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Parses a CSV file, converting each row into a text block key-value pairs.
    Ideal for database exports.
    """
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=2): # Start at 2 (header is 1)
                # Construct a readable text block from the CSV row
                content_lines = []
                for key, value in row.items():
                    if value and str(value).strip(): # Skip empty columns
                        content_lines.append(f"{key}: {value}")
                
                if not content_lines:
                    continue

                chunks.append({
                    "content": "\n".join(content_lines),
                    "source": str(file_path.name),
                    "line_start": str(idx),
                })
    except Exception as e:
         raise ValueError(f"Error parsing CSV: {e}")
            
    return chunks


def parse_json_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Parses a JSON file (list of objects), converting each object into text.
    """
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            data = [data] # Handle single object export

        for idx, entry in enumerate(data, start=1):
            if not isinstance(entry, dict):
                continue
                
            content_lines = []
            for key, value in entry.items():
                content_lines.append(f"{key}: {value}")

            chunks.append({
                "content": "\n".join(content_lines),
                "source": str(file_path.name),
                "line_start": str(idx),
            })
    except Exception as e:
        raise ValueError(f"Error parsing JSON: {e}")

    return chunks


def load_file(file_path: Path) -> List[Dict[str, str]]:
    """Dispatcher to load file based on extension."""
    if file_path.suffix.lower() == ".csv":
        return parse_csv_file(file_path)
    elif file_path.suffix.lower() == ".json":
        return parse_json_file(file_path)
    else:
        return parse_text_file(file_path)
```

---

## Phase 3: Update CLI to Support Formats

**Objective**: Update the ingest command to use the new `load_file` dispatcher.

### [MODIFY] logmind/commands/ingest_cmd.py

```python
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import track

from logmind.core.ai import AIClient
from logmind.core.db import VectorStore
from logmind.utils.parser import load_file  # Changed import

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
    Automatically detects CSV or JSON structure.
    """
    console.print(f"[bold blue]Processing file:[/bold blue] {file_path}")

    # 1. Parse Logs
    try:
        # Use the smart loader
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

## Phase 4: Documentation Update

**Objective**: Guide the user on how to handle Database logs.

### [MODIFY] README.md

(Add a new section under Usage)

```markdown
### 3. Database Logs (Shopware/Magento/Etc)

To analyze logs stored in a database:

1.  **Export the table** to CSV or JSON (e.g., via Adminer, phpMyAdmin, or SQL command).
2.  **Ingest the file**:
    ```bash
    logmind ingest path/to/shopware_export.csv
    ```

LogMind automatically detects `.csv` files and treats each row as a distinct log entry, preserving the column structure (e.g., `Exception`, `Response Body`) for better AI analysis.
```

---

## Phase 5: Implementation Report

Create `ai-plans/251216__IMPLEMENTATION_REPORT__structured-ingestion-shopware.md`.

```yaml
---
filename: "ai-plans/251216__IMPLEMENTATION_REPORT__structured-ingestion-shopware.md"
title: "Report: Add Structured Data Ingestion"
createdAt: 2025-12-16 10:20
updatedAt: 2025-12-16 10:20
plan_file: "ai-plans/251216__IMPLEMENTATION_PLAN__structured-ingestion-shopware.md"
project: "logmind"
status: completed
files_created: 0
files_modified: 3
files_deleted: 0
tags: [parser, csv, db]
documentType: IMPLEMENTATION_REPORT
---
```
