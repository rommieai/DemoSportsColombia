# app/services/embedding_service.py
import faiss
import numpy as np
from typing import List
from openai import OpenAI

class EmbeddingService:

    def __init__(self):
        self.client = OpenAI()
        self.dimension = 1536  # embedding 3-small
        self.index = faiss.IndexFlatL2(self.dimension)
        self.texts = []  # almacenamiento simple

    def embed(self, text: str) -> np.ndarray:
        emb = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return np.array(emb.data[0].embedding, dtype="float32")

    def store_snippets(self, snippets: List[str]):
        for t in snippets:
            vector = self.embed(t)
            self.index.add(np.array([vector]))
            self.texts.append(t)

    def query(self, query: str, k: int = 3) -> List[str]:
        qv = self.embed(query)
        distances, idx = self.index.search(np.array([qv]), k)
        return [self.texts[i] for i in idx[0] if i < len(self.texts)]
