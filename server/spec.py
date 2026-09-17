"""Tool specification: one YAML file per internal tool.

The YAML is the whole "app" - tables, forms, views, commands, dashboards and
permissions are all derived from it, the same way a Power Apps model-driven app
is derived from a Dataverse table.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

FieldType = Literal["text", "multiline", "number", "money", "boolean", "choice", "date", "datetime", "percent"]
Filter = dict[str, object]  # {field: value | [values] | {op: value}} | {any: [Filter, ...]}


def filter_fields(flt: Filter) -> list[str]:
    """Every field a filter reads, descending into `any` branches."""
    out: list[str] = []
    for k, v in flt.items():
        if k == "any" and isinstance(v, list):
            for sub in v:
                out.extend(filter_fields(sub))
        elif k not in out:
            out.append(k)
    return out


VERDICT_FIELD = "policy_verdict"
VERDICTS = ("Cleared", "Needs review", "Flagged")


class FieldSpec(BaseModel):
    name: str
    label: str | None = None
    type: FieldType = "text"
    required: bool = False
    options: list[str] = []
    default: object | None = None
    visible_to: list[str] | None = None  # column-level security; None = everyone
    mask: Literal["full", "last4"] = "full"
    readonly: bool = False
    width: int | None = None
    computed: bool = False  # derived at read time (e.g. policy verdict); never stored

    @model_validator(mode="after")
    def _check(self):
        if self.type == "choice" and not self.options:
            raise ValueError(f"field '{self.name}' is a choice but has no options")
        if self.label is None:
            self.label = self.name.replace("_", " ").capitalize()
        return self


class ViewSpec(BaseModel):
    id: str
    name: str
    filter: Filter = {}
    columns: list[str]
    sort: str | None = None  # "field asc|desc"
    mine: bool = False  # restrict to records where assignee == current user


class ActionSpec(BaseModel):
    id: str
    label: str
    roles: list[str]
    set: dict[str, object] = {}
    only_when: Filter = {}
    requires_comment: bool = False
    confirm: str | None = None
    webhook: str | None = None  # simulated integration (Power Automate equivalent)
    destructive: bool = False
    icon: str | None = None
    system: bool = False  # only runnable by automation (auto_review); hidden from the command bar


class CheckSpec(BaseModel):
    """One automated policy check: passes when `when` matches the record."""
    id: str
    clause: str  # e.g. KYC-2.1, resolves to a heading in knowledge/
    title: str
    when: Filter
    on_fail: Literal["flag", "review"] = "review"  # flag = policy breach, review = needs a human
    pass_text: str = ""
    fail_text: str = ""


class AutoReviewSpec(BaseModel):
    policy: str  # knowledge doc id
    scope: Filter = {}  # which records get reviewed
    clear_action: str | None = None  # run when every check passes
    flag_action: str | None = None  # run when a `flag` check fails
    actor: str = "devin-ai"


class TileSpec(BaseModel):
    type: Literal["kpi", "group", "series"]
    title: str
    metric: Literal["count", "sum", "avg"] = "count"
    field: str | None = None  # sum/avg field, or group-by field
    value_field: str | None = None  # sum/avg field when grouping (defaults to field)
    date_field: str | None = None
    days: int = 14
    filter: Filter = {}
    chart: Literal["bar", "donut", "hbar"] = "bar"
    format: Literal["number", "money", "percent", "hours"] = "number"


class PermissionSpec(BaseModel):
    read: list[str]
    create: list[str] = []
    update: list[str] = []
    export: list[str] = []


class ToolSpec(BaseModel):
    id: str
    name: str
    app: str
    description: str = ""
    icon: str = "grid"  # name from web/src/Icon.tsx
    entity: str
    title_field: str
    assignee_field: str | None = None
    fields: list[FieldSpec]
    views: list[ViewSpec]
    actions: list[ActionSpec] = []
    dashboard: list[TileSpec] = []
    checks: list[CheckSpec] = []
    auto_review: AutoReviewSpec | None = None
    permissions: PermissionSpec

    @model_validator(mode="after")
    def _check(self):
        if self.checks and not any(f.name == VERDICT_FIELD for f in self.fields):
            self.fields.append(FieldSpec(name=VERDICT_FIELD, label="Policy check", type="choice",
                                         options=list(VERDICTS), readonly=True, computed=True, width=135))
        names = {f.name for f in self.fields}
        if self.title_field not in names:
            raise ValueError(f"title_field '{self.title_field}' is not a field")
        for v in self.views:
            for c in v.columns:
                if c not in names:
                    raise ValueError(f"view '{v.id}' references unknown column '{c}'")
        for a in self.actions:
            for k in a.set:
                if k not in names:
                    raise ValueError(f"action '{a.id}' sets unknown field '{k}'")
        for t in self.dashboard:
            for f in (t.field, t.value_field, t.date_field):
                if f and f not in names:
                    raise ValueError(f"tile '{t.title}' references unknown field '{f}'")
        for c in self.checks:
            for f in filter_fields(c.when):
                if f not in names:
                    raise ValueError(f"check '{c.id}' references unknown field '{f}'")
        if self.auto_review:
            action_ids = {a.id for a in self.actions}
            for aid in (self.auto_review.clear_action, self.auto_review.flag_action):
                if aid and aid not in action_ids:
                    raise ValueError(f"auto_review references unknown action '{aid}'")
        return self

    @property
    def stored_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if not f.computed]

    def field(self, name: str) -> FieldSpec:
        return next(f for f in self.fields if f.name == name)


class User(BaseModel):
    id: str
    name: str
    roles: list[str]
    title: str = ""
    service: bool = False  # automation identity; cannot sign in, appears in audit as itself


class Directory(BaseModel):
    roles: dict[str, str]  # role -> description
    users: list[User]


def load_tools(directory: Path) -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        spec = ToolSpec.model_validate(yaml.safe_load(path.read_text()))
        tools[spec.id] = spec
    return tools


def load_directory(directory: Path) -> Directory:
    return Directory.model_validate(yaml.safe_load((directory / "_users.yaml").read_text()))
