import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from logmind.config import (
    COLLECTION_NAME,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_TIMEOUT_SECONDS,
    QDRANT_UPSERT_BATCH_SIZE,
    QDRANT_UPSERT_WAIT,
    VECTOR_SIZE,
)


class VectorStore:
    """
    Manages interactions with the Qdrant vector database.
    """

    def __init__(self) -> None:
        self.client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            timeout=QDRANT_TIMEOUT_SECONDS,
        )
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

    def get_status(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "host": QDRANT_HOST,
            "port": QDRANT_PORT,
            "collection": COLLECTION_NAME,
        }

        try:
            self.client.get_collections()
            status["connected"] = True
        except Exception as e:
            status["connected"] = False
            status["error"] = str(e)
            return status

        try:
            collection_exists = self.client.collection_exists(COLLECTION_NAME)
            status["collection_exists"] = collection_exists

            if collection_exists:
                info = self.client.get_collection(COLLECTION_NAME)
                status["collection_status"] = getattr(info, "status", None)
                status["points_count"] = getattr(info, "points_count", None)
                status["vectors_count"] = getattr(info, "vectors_count", None)
        except Exception as e:
            status["collection_error"] = str(e)

        return status

    def upsert_logs(
        self, logs: List[Dict[str, Any]], vectors: List[List[float]]
    ) -> None:
        """
        Stores log entries and their vectors in Qdrant.
        """
        if len(logs) != len(vectors):
            raise ValueError(
                f"logs/vectors length mismatch: logs={len(logs)} vectors={len(vectors)}"
            )

        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=log,
            )
            for log, vector in zip(logs, vectors)
        ]

        batch_size = max(1, int(QDRANT_UPSERT_BATCH_SIZE))
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch,
                wait=QDRANT_UPSERT_WAIT,
            )

    def search(self, vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches for the most relevant logs based on the query vector.
        """
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        return [point.payload for point in response.points if point.payload]
