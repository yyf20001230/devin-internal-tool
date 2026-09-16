"""HTTP API. Every endpoint is generic - adding a tool never touches this file."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai import OPENAI_MODEL, AIService, Provider, make_provider
from .engine import Engine, Forbidden, Invalid, NotFound
from .knowledge import load_knowledge
from .spec import ToolSpec, User, load_directory, load_tools

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(os.environ.get("TOOLS_DIR", ROOT / "tools"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", ROOT / "knowledge"))
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "data.db"))


class ActionBody(BaseModel):
    record_id: int
    comment: str | None = None


class SummaryBody(BaseModel):
    record_id: int


class ResetBody(BaseModel):
    record_id: int | None = None  # None resets every automated decision still in force
    comment: str | None = None


class QueryBody(BaseModel):
    question: str
    view: str | None = None


def build_app(tools_dir: Path = TOOLS_DIR, db_path: Path | str = DB_PATH,
              knowledge_dir: Path = KNOWLEDGE_DIR, provider: Provider | None = None) -> FastAPI:
    tools = load_tools(tools_dir)
    directory = load_directory(tools_dir)
    knowledge = load_knowledge(knowledge_dir)
    engine = Engine(db_path, tools)
    ai = AIService(engine, provider or make_provider(), knowledge.clause)
    for spec in tools.values():  # every check must cite a clause that exists in the knowledge base
        for c in spec.checks:
            if knowledge.clause(c.clause) is None:
                raise ValueError(f"{spec.id}: check '{c.id}' cites unknown clause {c.clause}")

    app = FastAPI(title="Internal Tools Platform")
    app.state.engine = engine
    app.state.directory = directory
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(Forbidden)
    async def _forbidden(_: Request, e: Forbidden):
        raise HTTPException(403, str(e))

    @app.exception_handler(NotFound)
    async def _notfound(_: Request, e: NotFound):
        raise HTTPException(404, str(e))

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, e: Invalid):
        raise HTTPException(400, str(e))

    # Auth is a stub: the front-end sends X-User. In production this is an OIDC/Entra ID
    # token validated by the reverse proxy, and roles come from group claims.
    def current_user(x_user: str = Header(default="")) -> User:
        user = next((u for u in directory.users if u.id == x_user and not u.service), None)
        if user is None:
            raise HTTPException(401, "unknown user")
        return user

    def service_user(user_id: str) -> User:
        user = next((u for u in directory.users if u.id == user_id and u.service), None)
        if user is None:
            raise HTTPException(500, f"service account {user_id} is not defined")
        return user

    def tool(tool_id: str, user: User = Depends(current_user)) -> ToolSpec:
        spec = tools.get(tool_id)
        if spec is None:
            raise HTTPException(404, f"tool {tool_id}")
        engine.require(spec, user, "read")
        return spec

    @app.get("/api/me")
    def me(user: User = Depends(current_user)):
        return {"user": user, "roles": directory.roles, "tools": [
            {"id": t.id, "name": t.name, "app": t.app, "description": t.description, "icon": t.icon,
             "can": {op: bool(set(user.roles) & set(getattr(t.permissions, op)))
                     for op in ("read", "create", "update", "export")}}
            for t in engine.visible_tools(user)
        ]}

    @app.get("/api/users")
    def users():
        return [u for u in directory.users if not u.service]  # demo sign-in page; stands in for Entra ID

    @app.get("/api/knowledge")
    def knowledge_index(user: User = Depends(current_user)):
        return [{"id": d.id, "title": d.title, "summary": d.summary, "clauses": len(d.clauses)}
                for d in knowledge.docs.values()]

    @app.get("/api/knowledge/{doc_id}")
    def knowledge_doc(doc_id: str, user: User = Depends(current_user)):
        doc = knowledge.docs.get(doc_id)
        if doc is None:
            raise HTTPException(404, f"policy {doc_id}")
        return doc

    @app.get("/api/tools/{tool_id}")
    def get_tool(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        can = lambda roles: bool(set(user.roles) & set(roles))  # noqa: E731
        d = spec.model_dump()
        for f in d["fields"]:
            f["masked"] = f["visible_to"] is not None and not can(f["visible_to"])
        d["actions"] = [a for a in d["actions"] if not a["system"]]
        for a in d["actions"]:
            a["allowed"] = can(a["roles"])
        d["can"] = {op: can(getattr(spec.permissions, op)) for op in ("read", "create", "update", "export")}
        return d

    @app.get("/api/tools/{tool_id}/records")
    def list_records(spec: ToolSpec = Depends(tool), user: User = Depends(current_user),
                     view: str | None = None, q: str = ""):
        return engine.list_records(spec, user, view, q)

    @app.get("/api/tools/{tool_id}/records.csv", response_class=PlainTextResponse)
    def export(spec: ToolSpec = Depends(tool), user: User = Depends(current_user), view: str | None = None):
        return engine.export_csv(spec, user, view)

    @app.post("/api/tools/{tool_id}/records", status_code=201)
    def create(values: dict, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.create_record(spec, user, values)

    @app.get("/api/tools/{tool_id}/records/{rid}")
    def get_record(rid: int, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.get_record(spec, user, rid)

    @app.patch("/api/tools/{tool_id}/records/{rid}")
    def update(rid: int, values: dict, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.update_record(spec, user, rid, values)

    @app.post("/api/tools/{tool_id}/actions/{action_id}")
    def action(action_id: str, body: ActionBody, spec: ToolSpec = Depends(tool),
               user: User = Depends(current_user)):
        return engine.run_action(spec, user, action_id, body.record_id, body.comment)

    @app.get("/api/tools/{tool_id}/records/{rid}/review")
    def record_review(rid: int, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        res = engine.record_review(spec, user, rid)
        cite(res["checks"])
        res["policy"] = spec.auto_review.policy if spec.auto_review else None
        res["ai_decision"] = engine.ai_decision(spec, rid)
        return res

    @app.get("/api/tools/{tool_id}/ai-decisions")
    def ai_decisions(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return {"records": engine.ai_decided(spec, user)}

    @app.post("/api/tools/{tool_id}/ai-reset")
    def ai_reset(body: ResetBody, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        if body.record_id is None:
            return engine.reset_ai_all(spec, user, body.comment)
        return {"reset": [body.record_id], "record": engine.reset_ai(spec, user, body.record_id, body.comment)}

    @app.post("/api/tools/{tool_id}/auto-review")
    def auto_review(spec: ToolSpec = Depends(tool), user: User = Depends(current_user),
                    view: str | None = None):
        if spec.auto_review is None:
            raise HTTPException(400, f"{spec.name} has no auto-review policy")
        report = engine.auto_review(spec, user, service_user(spec.auto_review.actor), view)
        for item in report["items"]:
            cite(item["checks"])
        doc = knowledge.docs.get(spec.auto_review.policy)
        report["policy_title"] = doc.title if doc else spec.auto_review.policy
        return report

    def cite(checks: list[dict]) -> None:
        """Attach the knowledge-base clause (title, text, source doc) to each check result."""
        for c in checks:
            clause = knowledge.clause(c["clause"])
            c["clause_title"] = clause.title if clause else ""
            c["clause_text"] = clause.text if clause else ""
            c["policy"] = clause.doc if clause else None

    @app.post("/api/tools/{tool_id}/ai/summary")
    def ai_summary(body: SummaryBody, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return ai.summarize(spec, user, body.record_id)

    @app.post("/api/tools/{tool_id}/ai/query")
    def ai_query(body: QueryBody, spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        if not body.question.strip():
            raise HTTPException(400, "ask something")
        return ai.query(spec, user, body.question, body.view)

    @app.get("/api/ai")
    def ai_status(user: User = Depends(current_user)):
        return {"provider": ai.provider.name, "model": OPENAI_MODEL if ai.provider.name == "openai" else None,
                "last_error": ai.provider.last_error}

    @app.get("/api/tools/{tool_id}/dashboard")
    def dashboard(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.dashboard(spec, user)

    @app.get("/api/tools/{tool_id}/audit")
    def audit(spec: ToolSpec = Depends(tool), user: User = Depends(current_user),
              record_id: int | None = Query(default=None)):
        return engine.audit(spec, user, record_id)

    @app.get("/api/tools/{tool_id}/integrations")
    def integrations(spec: ToolSpec = Depends(tool), user: User = Depends(current_user)):
        return engine.integrations(spec, user)

    dist = ROOT / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = build_app()
