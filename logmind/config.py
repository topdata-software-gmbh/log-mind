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
