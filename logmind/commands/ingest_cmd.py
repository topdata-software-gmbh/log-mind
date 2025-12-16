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
