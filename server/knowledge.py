"""Knowledge base: markdown policy documents whose `### CODE Title` headings are citable clauses.

Policy checks in a tool YAML cite a clause code (e.g. KYC-2.1); the UI shows the clause text
next to the check so a reviewer sees *why* something was cleared or flagged.
"""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

CLAUSE_RE = re.compile(r"^### ([A-Z]+-\d+(?:\.\d+)?) (.+)$")


class Clause(BaseModel):
    code: str
    title: str
    text: str
    doc: str


class Doc(BaseModel):
    id: str
    title: str
    summary: str
    body: str
    clauses: list[Clause]


class Knowledge(BaseModel):
    docs: dict[str, Doc]

    def clause(self, code: str) -> Clause | None:
        for d in self.docs.values():
            for c in d.clauses:
                if c.code == code:
                    return c
        return None


def parse_doc(doc_id: str, body: str) -> Doc:
    title = doc_id
    summary = ""
    clauses: list[Clause] = []
    current: Clause | None = None
    buf: list[str] = []

    def flush() -> None:
        if current is not None:
            current.text = "\n".join(buf).strip()
            clauses.append(current)

    for line in body.splitlines():
        if line.startswith("# ") and title == doc_id:
            title = line[2:].strip()
            continue
        m = CLAUSE_RE.match(line)
        if m:
            flush()
            current = Clause(code=m.group(1), title=m.group(2).strip(), text="", doc=doc_id)
            buf = []
            continue
        if line.startswith("#"):
            flush()
            current = None
            buf = []
            continue
        if current is not None:
            buf.append(line)
        elif not summary and line.strip() and not line.startswith(">"):
            summary = line.strip()
    flush()
    return Doc(id=doc_id, title=title, summary=summary, body=body, clauses=clauses)


def load_knowledge(directory: Path) -> Knowledge:
    docs: dict[str, Doc] = {}
    if directory.exists():
        for path in sorted(directory.glob("*.md")):
            docs[path.stem] = parse_doc(path.stem, path.read_text())
    return Knowledge(docs=docs)
