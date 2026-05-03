import os
import json
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./memory/chroma_store")
COLLECTION  = "sre_incidents"

_chroma_client     = None
_collection        = None
_embedding_fn      = None


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _embedding_fn


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION,
            embedding_function=_get_embedding_fn(),
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


def store_incident_vector(
    incident_id: str,
    anomaly_type: str,
    issue: str,
    root_cause: str,
    action_taken: str,
    outcome: str,
    namespace: str,
    pod: str
):
    """Store an incident as a vector embedding for future similarity search."""
    col = _get_collection()

    # Build the text document that will be embedded
    document = f"""
Anomaly: {anomaly_type}
Issue: {issue}
Root Cause: {root_cause}
Action Taken: {action_taken}
Outcome: {outcome}
Namespace: {namespace}
Pod: {pod}
    """.strip()

    metadata = {
        "anomaly_type": anomaly_type,
        "issue": issue,
        "action_taken": action_taken,
        "outcome": outcome,
        "namespace": namespace,
        "pod": pod
    }

    col.upsert(
        ids=[incident_id],
        documents=[document],
        metadatas=[metadata]
    )
    print(f"  [Vector DB] Stored incident {incident_id[:8]}")


def query_similar_incidents(
    anomaly_type: str,
    issue: str,
    root_cause: str,
    n_results: int = 3
) -> list[dict]:
    """Find past incidents similar to the current one using vector similarity."""
    col = _get_collection()

    if col.count() == 0:
        return []

    query_text = f"Anomaly: {anomaly_type}\nIssue: {issue}\nRoot Cause: {root_cause}"

    results = col.query(
        query_texts=[query_text],
        n_results=min(n_results, col.count())
    )

    similar = []
    for i, doc in enumerate(results["documents"][0]):
        similar.append({
            "id":          results["ids"][0][i],
            "document":    doc,
            "metadata":    results["metadatas"][0][i],
            "distance":    results["distances"][0][i]
        })

    return similar


def get_collection_size() -> int:
    return _get_collection().count()