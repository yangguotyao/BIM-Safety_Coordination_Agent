"""Supported acceptance criteria are data, not arbitrary executable rules."""
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class VerificationCriteria(BaseModel):
    model_config = ConfigDict(extra='forbid')
    guardrail_required: bool = True
    min_height_m: float = Field(default=1.2, ge=1.2, le=3.0, allow_inf_nan=False)
    fixed_required: bool = True
    continuous_required: bool = True
    coordination_required: bool = False
    manual_requirements: list[str] = Field(default_factory=list, max_length=12)


def normalize_criteria(control: dict[str, Any], *, modified: bool = False) -> dict[str, Any]:
    raw = control.get('verification_criteria')
    if raw is not None:
        criteria = VerificationCriteria.model_validate(raw)
    else:
        criteria = VerificationCriteria()
    if modified:
        text = control.get('action', '')
        # Only an explicit height in a guardrail/height sentence is interpreted.
        sentences = re.findall(r'(?:栏杆|高度|rail|height)[^。;；\n]{0,160}', text, re.I)
        heights = []
        for sentence in sentences:
            for value, unit in re.findall(r'(\d+(?:\.\d+)?)\s*(mm|cm|m|米)', sentence, re.I):
                heights.append(float(value) * (.001 if unit.lower()=='mm' else .01 if unit.lower()=='cm' else 1))
        if heights:
            criteria.min_height_m=max(criteria.min_height_m, *heights)
            criteria=VerificationCriteria.model_validate(criteria.model_dump())
        # Text modifications can contain requirements outside numeric automation.
        if not criteria.manual_requirements:
            criteria.manual_requirements=['逐项确认修改后的文字措施与验收要求已满足。']
    return criteria.model_dump()


def approved_criteria(case: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = (case.get('review') or {}).get('verification_snapshot')
    if snapshot:
        return list(snapshot.values())
    return [normalize_criteria(c) for c in case.get('controls', [])] or [VerificationCriteria().model_dump()]
