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
