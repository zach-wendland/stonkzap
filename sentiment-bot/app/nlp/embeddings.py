import numpy as np

def compute_embedding(text: str) -> np.ndarray:
    # Placeholder: simple hash-based embedding
    # TODO: Replace with sentence-transformers or similar
    np.random.seed(hash(text) % (2**32))
    emb = np.random.randn(768).astype(np.float32)
    # Normalize
    emb = emb / np.linalg.norm(emb)
    return emb
