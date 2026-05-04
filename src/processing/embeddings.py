import numpy as np
from functools import lru_cache
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(_MODEL_NAME)


class Embedder:
    def __init__(self):
        self._model = _get_model()

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("embed() requires non-empty text")
        vec = self._model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        if len(v1) != len(v2):
            raise ValueError(f"Vector length mismatch: {len(v1)} vs {len(v2)}")
        a = np.array(v1)
        b = np.array(v2)
        return float(np.dot(a, b))  # Vectors are already L2-normalized
