from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .models import SourceBlock
from .utils import cosine, normalize_text_key, tokens


@dataclass(frozen=True)
class RankedBlock:
    block: SourceBlock
    score: float
    rank: int


def bm25(blocks: list[SourceBlock], queries: list[str], top_k: int, k1: float = 1.5, b: float = 0.75) -> list[RankedBlock]:
    usable = [x for x in blocks if x.block_type != "reference"]
    docs = [tokens(x.text) for x in usable]
    if not docs:
        return []
    avgdl = sum(map(len, docs)) / len(docs)
    dfs = Counter(term for doc in docs for term in set(doc))
    query_tokens = [tokens(q) for q in queries]
    scores = []
    for block, doc in zip(usable, docs):
        tf = Counter(doc)
        per_query = []
        for query in query_tokens:
            score = 0.0
            for term in query:
                n = dfs.get(term, 0)
                idf = math.log(1 + (len(docs) - n + 0.5) / (n + 0.5))
                frequency = tf.get(term, 0)
                denom = frequency + k1 * (1 - b + b * len(doc) / max(avgdl, 1))
                score += idf * frequency * (k1 + 1) / denom if denom else 0
            per_query.append(score)
        scores.append((max(per_query, default=0), block))
    scores.sort(key=lambda x: (-x[0], x[1].order))
    return [RankedBlock(block, score, rank) for rank, (score, block) in enumerate(scores[:top_k], 1)]


def semantic(blocks: list[SourceBlock], query_vectors: list[list[float]], top_k: int) -> list[RankedBlock]:
    scored = []
    for block in blocks:
        if block.block_type != "reference" and block.embedding:
            scored.append((max((cosine(block.embedding, q) for q in query_vectors), default=0), block))
    scored.sort(key=lambda x: (-x[0], x[1].order))
    return [RankedBlock(block, score, rank) for rank, (score, block) in enumerate(scored[:top_k], 1)]


def exact_alias_hit(block: SourceBlock, aliases: list[str]) -> bool:
    text = normalize_text_key(block.text)
    return any(normalize_text_key(alias) in text for alias in aliases if normalize_text_key(alias))

