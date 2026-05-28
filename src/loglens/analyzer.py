from __future__ import annotations

from typing import Protocol

from .models import LogRecord


class Analyzer(Protocol):
    def query(
        self, records: list[LogRecord], text: str, top_k: int
    ) -> list[tuple[LogRecord, float]]: ...


_AI_HINT = (
    "Semantic query requires the 'ai' extra. "
    "Install it with: pip install loglens[ai]"
)


class EmbeddingQuery:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            from rank_bm25 import BM25Okapi  # noqa: F401
        except ImportError as e:
            raise RuntimeError(_AI_HINT) from e

        self._SentenceTransformer = SentenceTransformer
        self._BM25Okapi = BM25Okapi
        self._model = SentenceTransformer(model_name)

    @staticmethod
    def _key(r: LogRecord) -> str:
        return r.template_id or f"_raw:{r.seq}"

    @staticmethod
    def _text_for(r: LogRecord) -> str:
        return r.template or r.message

    @staticmethod
    def _cosine(a, b) -> float:
        import numpy as np

        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)

    def query(
        self, records: list[LogRecord], text: str, top_k: int = 10
    ) -> list[tuple[LogRecord, float]]:
        if not records:
            return []

        # Dedup by template_id, keep first record as representative.
        unique: dict[str, LogRecord] = {}
        for r in records:
            unique.setdefault(self._key(r), r)
        reps = list(unique.values())
        texts = [self._text_for(r) for r in reps]

        # Embed.
        rep_emb = self._model.encode(texts, normalize_embeddings=True)
        q_emb = self._model.encode([text], normalize_embeddings=True)[0]

        # BM25 over tokenized templates.
        tokenized = [t.lower().split() for t in texts]
        bm25 = self._BM25Okapi(tokenized)
        bm25_scores = bm25.get_scores(text.lower().split())
        max_bm = float(max(bm25_scores)) if len(bm25_scores) else 0.0
        norm_bm = [
            (float(s) / max_bm) if max_bm > 0 else 0.0 for s in bm25_scores
        ]

        scored: list[tuple[LogRecord, float]] = []
        for rep, emb, bm in zip(reps, rep_emb, norm_bm):
            cos = self._cosine(emb, q_emb)
            score = 0.7 * cos + 0.3 * bm
            scored.append((rep, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
