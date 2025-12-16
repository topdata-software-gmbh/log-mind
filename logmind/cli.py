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
