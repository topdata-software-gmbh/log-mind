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
    try:
        db = VectorStore()
    except Exception as e:
        console.print(f"[bold red]Qdrant init failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    status = db.get_status()
    if status.get("connected") is True:
        console.print(
            "[bold green]Qdrant:[/bold green] "
            f"{status.get('host')}:{status.get('port')} "
            f"collection={status.get('collection')} "
            f"exists={status.get('collection_exists')} "
            f"points={status.get('points_count')}"
        )
    else:
        console.print(
            "[bold red]Qdrant:[/bold red] "
            f"{status.get('host')}:{status.get('port')} "
            f"collection={status.get('collection')} "
            f"connected=False "
            f"error={status.get('error')}"
        )

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
            console.print(
                f"[yellow]Skipped {skipped_count} entries due to embedding errors/size limits.[/yellow]"
            )

        if logs_to_store:
            console.print(f"[yellow]Storing {len(logs_to_store)} entries in Qdrant...[/yellow]")
            db.upsert_logs(logs_to_store, vectors)
            console.print("[bold green]Ingestion complete![/bold green]")
        else:
            console.print("[bold red]No valid logs to store.[/bold red]")

    except Exception as e:
        console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
        raise typer.Exit(code=1)
