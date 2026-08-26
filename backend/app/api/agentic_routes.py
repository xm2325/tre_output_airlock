from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.agent_schemas import AgentAssistOut, AgentAssistRequest
from app.api.common import _get_submission, _request_id
from app.core.auth import Actor, get_actor
from app.db import get_db
from app.services.agentic_assist import (
    AgentRequestRejected,
    AgentToolDenied,
    objective_digest,
    run_agent_assist,
)
from app.services.audit import append_audit_event

router = APIRouter()


@router.post(
    "/api/v1/submissions/{submission_id}/agent-assist",
    response_model=AgentAssistOut,
    tags=["agentic-ai"],
)
def agent_assist(
    request: Request,
    submission_id: str,
    payload: AgentAssistRequest,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> AgentAssistOut:
    submission = _get_submission(db, submission_id, actor)
    digest = objective_digest(payload.objective)

    try:
        result = run_agent_assist(submission, actor, payload.objective)
    except AgentRequestRejected as exc:
        append_audit_event(
            submission,
            "AGENT_ASSIST_REJECTED",
            actor.name,
            f"reason=instruction_override; objective_sha256={digest}",
            _request_id(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent request rejected by the instruction-override control.",
        ) from exc
    except AgentToolDenied as exc:
        append_audit_event(
            submission,
            "AGENT_TOOL_DENIED",
            actor.name,
            f"reason=role_policy; objective_sha256={digest}",
            _request_id(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The requested agent plan contains a tool not permitted for this role.",
        ) from exc

    tools = ",".join(result.tools_used)
    action = result.proposed_action or "none"
    append_audit_event(
        submission,
        "AGENT_ASSIST_COMPLETED",
        actor.name,
        (
            f"tools={tools}; proposed_action={action}; "
            f"human_approval={str(result.requires_human_approval).lower()}; "
            f"objective_sha256={digest}"
        ),
        _request_id(request),
    )
    db.commit()
    return result
