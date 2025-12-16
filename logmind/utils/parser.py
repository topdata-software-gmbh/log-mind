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
