from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import Decision, Role

AgentToolName = Literal[
    "get_submission_context",
    "get_policy_evidence",
    "propose_release_action",
]
AgentToolOutcome = Literal["OK", "DENIED", "REJECTED"]


class AgentAssistRequest(BaseModel):
    objective: str = Field(min_length=10, max_length=800)


class AgentToolTrace(BaseModel):
    tool: AgentToolName
    outcome: AgentToolOutcome
    detail: str


class AgentAssistOut(BaseModel):
    contract_version: str
    submission_id: str
    actor_role: Role
    objective_sha256: str
    tools_used: list[AgentToolName]
    proposed_action: Decision | None
    requires_human_approval: bool
    policy_version: str
    risk_score: float
    risk_band: str
    evidence: list[str]
    safety_flags: list[str]
    trace: list[AgentToolTrace]
    disclaimer: str
