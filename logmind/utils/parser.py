import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def parse_text_file(file_path: Path, chunk_size: int = 15) -> List[Dict[str, str]]:
    """Reads a raw log file and groups lines into chunks."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")

    chunks: List[Dict[str, str]] = []
    for i in range(0, len(lines), chunk_size):
        chunk_content = "".join(lines[i : i + chunk_size])
        chunks.append(
            {
                "content": chunk_content,
                "source": file_path.name,
                "line_start": str(i + 1),
            }
        )
    return chunks


def parse_csv_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Parses a CSV file, converting each row into a text block of key-value pairs.
    Ideal for database exports.
    """
    chunks: List[Dict[str, str]] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=2):  # header line counts as 1
                content_lines = []
                for key, value in row.items():
                    if value and str(value).strip():
                        content_lines.append(f"{key}: {value}")

                if not content_lines:
                    continue

                chunks.append(
                    {
                        "content": "\n".join(content_lines),
                        "source": file_path.name,
                        "line_start": str(idx),
                    }
                )
    except Exception as exc:
        raise ValueError(f"Error parsing CSV: {exc}") from exc

    return chunks


def parse_json_file(file_path: Path) -> List[Dict[str, str]]:
    """Parses a JSON file (list or single object), converting objects into text."""
    chunks: List[Dict[str, str]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data: Any = json.load(f)

        if not isinstance(data, list):
            data = [data]

        for idx, entry in enumerate(data, start=1):
            if not isinstance(entry, dict):
                continue

            content_lines = [f"{key}: {value}" for key, value in entry.items()]
            if not content_lines:
                continue

            chunks.append(
                {
                    "content": "\n".join(content_lines),
                    "source": file_path.name,
                    "line_start": str(idx),
                }
            )
    except Exception as exc:
        raise ValueError(f"Error parsing JSON: {exc}") from exc

    return chunks


def load_file(file_path: Path) -> List[Dict[str, str]]:
    """Dispatcher to load file based on extension."""
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return parse_csv_file(file_path)
    if suffix == ".json":
        return parse_json_file(file_path)
    return parse_text_file(file_path)
