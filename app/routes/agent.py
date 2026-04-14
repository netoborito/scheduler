"""Agent-facing API endpoints for LLM/tool integrations."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.preferences_service import (
    load_preferences,
    save_preferences,
    validate_rule,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PreferenceRule(BaseModel):
    match: Dict[str, str]
    set: Dict[str, str]


class PreferencesPayload(BaseModel):
    rules: List[PreferenceRule]


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------


@router.get("/preferences")
async def get_preferences() -> dict:
    """Return current optimizer preference rules."""
    return {"rules": load_preferences()}


@router.put("/preferences")
async def put_preferences(payload: PreferencesPayload) -> dict:
    """Replace optimizer preference rules (validates regex patterns)."""
    rules = [r.model_dump() for r in payload.rules]
    for i, rule in enumerate(rules):
        try:
            validate_rule(rule)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Rule {i}: {e}")
    save_preferences(rules)
    return {"status": "ok", "count": len(rules)}
