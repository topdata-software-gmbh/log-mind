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

### 3. Database Logs (Shopware/Magento/Etc)

To analyze logs stored in a database:

1. **Export the table** to CSV or JSON (e.g., via Adminer, phpMyAdmin, or SQL command).
2. **Ingest the file**:

    ```bash
    logmind ingest path/to/shopware_export.csv
    ```

LogMind automatically detects `.csv` or `.json` files and treats each row/object as a distinct log entry, preserving the column structure (for example `exception_class`, `response_body`) for better AI analysis.

## Development

- **Format Code**: `uv run ruff format .`
- **Lint Code**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`
