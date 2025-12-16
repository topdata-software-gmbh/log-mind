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
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()),
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
