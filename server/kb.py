"""Knowledge base index: the policy documents as a searchable vector store.

`knowledge/*.md` stays the source of truth (reviewed through PRs like code). At startup each clause
becomes a chunk, chunks are embedded and stored in SQLite (`kb_chunks`), and AI features retrieve
the clauses relevant to a record or question from this index rather than reading the files.

Two embedders behind one interface:
  * OpenAIEmbedder   - text-embedding-3-small, used when OPENAI_API_KEY is set
  * LexicalEmbedder  - deterministic hashed TF-IDF vectors, so search works offline and in tests

Embeddings are cached by content hash; unchanged clauses are never re-embedded.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Protocol

import httpx
from pydantic import BaseModel

from .knowledge import Knowledge

EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
_TOKEN = re.compile(r"[a-z][a-z0-9\-]+")
_STOP = {"the", "and", "for", "are", "with", "that", "this", "not", "may", "any", "its", "all", "only",
         "when", "than", "from", "must", "into", "have", "has", "been", "was", "were", "will", "each",
         "per", "one", "two", "does", "did", "who", "what", "which", "where", "why", "how", "case", "cases"}


class Chunk(BaseModel):
    id: str            # "<doc>#<clause code>" or "<doc>#intro"
    doc: str
    doc_title: str
    clause: str | None
    title: str
    text: str


class Hit(BaseModel):
    chunk: Chunk
    score: float


class Embedder(Protocol):
    name: str
    model: str
    last_error: str | None

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LexicalEmbedder:
    """Hashed bag-of-words with sub-linear tf; no model, no network. Good enough for ~50 clauses."""
    name = "lexical"
    model = "hashed-tfidf-512"
    last_error = None
    DIM = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            vec = [0.0] * self.DIM
            for tok, n in Counter(self._tokens(t)).items():
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % self.DIM] += (1 + math.log(n)) * (1 if (h >> 64) & 1 else -1)
            out.append(vec)
        return out

    @staticmethod
    def _tokens(text: str) -> list[str]:
        toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        return toks + [t[:5] for t in toks if len(t) > 6]  # crude stemming: "verified" ~ "verification"


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str, fallback: LexicalEmbedder):
        self.key = api_key
        self.model = EMBEDDING_MODEL
        self.fallback = fallback
        self.last_error: str | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"model": self.model, "input": texts},
            timeout=30,
        )
        if r.status_code >= 400:
            try:
                detail = r.json()["error"]["code"] or r.json()["error"]["message"]
            except (ValueError, KeyError):
                detail = r.text[:120]
            raise httpx.HTTPStatusError(f"{r.status_code} {detail}", request=r.request, response=r)
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]


def make_embedder() -> Embedder:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    lexical = LexicalEmbedder()
    return OpenAIEmbedder(key, lexical) if key else lexical


def chunk_knowledge(kb: Knowledge) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d in kb.docs.values():
        if d.summary:
            chunks.append(Chunk(id=f"{d.id}#intro", doc=d.id, doc_title=d.title, clause=None,
                                title=d.title, text=d.summary))
        for c in d.clauses:
            chunks.append(Chunk(id=f"{d.id}#{c.code}", doc=d.id, doc_title=d.title, clause=c.code,
                                title=c.title, text=c.text))
    return chunks


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class KnowledgeBase:
    """Vector index over the policy clauses, persisted in the platform's SQLite database."""

    def __init__(self, conn: sqlite3.Connection, knowledge: Knowledge, embedder: Embedder):
        self.conn = conn
        self.knowledge = knowledge
        self.embedder = embedder
        self.active: Embedder = embedder  # what the index was actually built with
        self.chunks = chunk_knowledge(knowledge)
        self._vectors: dict[str, list[float]] = {}
        self.indexed_at: str | None = None
        self.last_error: str | None = None
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS kb_chunks (id TEXT NOT NULL, model TEXT NOT NULL, hash TEXT NOT NULL, "
            "doc TEXT NOT NULL, vector TEXT NOT NULL, indexed_at TEXT NOT NULL, PRIMARY KEY (id, model))"
        )
        self.conn.commit()
        self.reindex()

    # ---- indexing ---------------------------------------------------------------------------
    @staticmethod
    def _hash(c: Chunk) -> str:
        return hashlib.sha256(f"{c.title}\n{c.text}".encode()).hexdigest()[:16]

    def _embed_text(self, c: Chunk) -> str:
        return f"{c.doc_title} — {c.clause + ' ' if c.clause else ''}{c.title}\n{c.text}"

    def reindex(self) -> dict:
        """Embed clauses whose content changed since the last run; drop clauses that no longer exist."""
        t0 = time.monotonic()
        model = self.embedder.model
        cached = {r["id"]: r for r in self.conn.execute("SELECT * FROM kb_chunks WHERE model=?", (model,))}
        stale = [c for c in self.chunks if c.id not in cached or cached[c.id]["hash"] != self._hash(c)]
        embedded = 0
        try:
            if stale:
                vecs = self.embedder.embed([self._embed_text(c) for c in stale])
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for c, v in zip(stale, vecs):
                    self.conn.execute(
                        "INSERT OR REPLACE INTO kb_chunks (id, model, hash, doc, vector, indexed_at) VALUES (?,?,?,?,?,?)",
                        (c.id, model, self._hash(c), c.doc, json.dumps(v), now),
                    )
                embedded = len(stale)
            self.active = self.embedder
            self.last_error = None
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # Provider unavailable (quota, network, bad key): serve search from the lexical index so the
            # tools keep working; the next reindex() retries the real embedder.
            self.last_error = str(e)[:160]
            fallback = getattr(self.embedder, "fallback", None)
            if fallback is None:
                raise
            self.active = fallback
            model = fallback.model
            vecs = fallback.embed([self._embed_text(c) for c in self.chunks])
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for c, v in zip(self.chunks, vecs):
                self.conn.execute(
                    "INSERT OR REPLACE INTO kb_chunks (id, model, hash, doc, vector, indexed_at) VALUES (?,?,?,?,?,?)",
                    (c.id, model, self._hash(c), c.doc, json.dumps(v), now),
                )
            embedded = len(self.chunks)
        live_ids = {c.id for c in self.chunks}
        for cid in list(cached):
            if cid not in live_ids:
                self.conn.execute("DELETE FROM kb_chunks WHERE id=? AND model=?", (cid, model))
        self.conn.commit()
        self._vectors = {r["id"]: json.loads(r["vector"])
                         for r in self.conn.execute("SELECT id, vector FROM kb_chunks WHERE model=?", (model,))}
        self.indexed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {"chunks": len(self.chunks), "embedded": embedded, "reused": len(self.chunks) - embedded,
                "backend": self.active.name, "model": model, "ms": int((time.monotonic() - t0) * 1000)}

    def reload(self, knowledge: Knowledge) -> dict:
        """Swap in freshly parsed documents and embed only what changed."""
        self.knowledge = knowledge
        self.chunks = chunk_knowledge(knowledge)
        return self.reindex()

    # ---- retrieval --------------------------------------------------------------------------
    def search(self, query: str, k: int = 5, docs: list[str] | None = None, min_score: float = 0.0) -> list[Hit]:
        if not query.strip() or not self._vectors:
            return []
        try:
            qv = self.active.embed([query])[0]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            self.last_error = str(e)[:160]
            fallback = getattr(self.active, "fallback", None)
            if fallback is None:
                raise
            self.active = fallback
            self.reindex()
            qv = fallback.embed([query])[0]
        hits = []
        for c in self.chunks:
            if docs and c.doc not in docs:
                continue
            v = self._vectors.get(c.id)
            if v is None:
                continue
            s = _cos(qv, v)
            if s >= min_score:
                hits.append(Hit(chunk=c, score=round(s, 4)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]

    def status(self) -> dict:
        return {
            "backend": self.active.name,
            "model": self.active.model,
            "configured": self.embedder.name,
            "chunks": len(self.chunks),
            "docs": [d.id for d in self.knowledge.docs.values()],
            "indexed_at": self.indexed_at,
            "last_error": self.last_error,
        }
