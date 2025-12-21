"""
MithrilLog Governance API

REST endpoints for:
- Data Enablement Plan management
- Compliance checking
- Audit logging
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("mithrillog.api.governance")

router = APIRouter(prefix="/api/governance", tags=["Governance"])


# --- Request/Response Models ---

class CreateDEPRequest(BaseModel):
    """Create DEP request."""
    tenant_id: str
    name: str
    description: str = ""
    owner: str
    privacy_classification: str = "internal"
    data_source: str = ""
    data_elements: List[str] = []
    encryption_required: bool = True
    access_controls: List[str] = []
    retention_days: int = Field(90, ge=1, le=3650)
    data_handling_notes: str = ""
    masking_rules: Dict[str, str] = {}


class UpdateDEPRequest(BaseModel):
    """Update DEP request."""
    name: Optional[str] = None
    description: Optional[str] = None
    privacy_classification: Optional[str] = None
    data_source: Optional[str] = None
    data_elements: Optional[List[str]] = None
    encryption_required: Optional[bool] = None
    access_controls: Optional[List[str]] = None
    retention_days: Optional[int] = None
    data_handling_notes: Optional[str] = None
    masking_rules: Optional[Dict[str, str]] = None


class ApprovalRequest(BaseModel):
    """DEP approval request."""
    approver: str
    expires_days: int = Field(365, ge=30, le=1095)


class RejectionRequest(BaseModel):
    """DEP rejection request."""
    approver: str
    reason: str


class ComplianceCheckRequest(BaseModel):
    """Compliance check request."""
    text: str
    max_pii_count: int = 0
    allowed_pii_types: Optional[List[str]] = None


class LogScanRequest(BaseModel):
    """Log scan request."""
    logs: List[Dict[str, Any]]


# --- DEP Endpoints ---

@router.post("/deps")
async def create_dep(request: CreateDEPRequest):
    """Create a new Data Enablement Plan."""
    from mithrillog.governance.dep_manager import get_dep_manager, PrivacyClassification
    
    manager = get_dep_manager()
    
    try:
        classification = PrivacyClassification(request.privacy_classification)
    except ValueError:
        raise HTTPException(400, f"Invalid privacy classification: {request.privacy_classification}")
    
    dep = manager.create_dep(
        tenant_id=request.tenant_id,
        name=request.name,
        description=request.description,
        owner=request.owner,
        privacy_classification=classification,
        data_source=request.data_source,
        data_elements=request.data_elements,
        encryption_required=request.encryption_required,
        access_controls=request.access_controls,
        retention_days=request.retention_days,
        data_handling_notes=request.data_handling_notes,
        masking_rules=request.masking_rules,
    )
    
    return {"success": True, "dep": dep.to_dict()}


@router.get("/deps")
async def list_deps(
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """List Data Enablement Plans."""
    from mithrillog.governance.dep_manager import get_dep_manager, DEPStatus
    
    manager = get_dep_manager()
    
    status_filter = None
    if status:
        try:
            status_filter = DEPStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    
    deps = manager.list_deps(tenant_id=tenant_id, status=status_filter)
    
    return {
        "count": len(deps),
        "deps": [d.to_dict() for d in deps],
    }


@router.get("/deps/{dep_id}")
async def get_dep(dep_id: str):
    """Get a specific DEP."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    dep = manager.get_dep(dep_id)
    
    if not dep:
        raise HTTPException(404, f"DEP not found: {dep_id}")
    
    return {"dep": dep.to_dict()}


@router.patch("/deps/{dep_id}")
async def update_dep(dep_id: str, request: UpdateDEPRequest, actor: str = Query(...)):
    """Update a DEP."""
    from mithrillog.governance.dep_manager import get_dep_manager, PrivacyClassification
    
    manager = get_dep_manager()
    
    updates = request.dict(exclude_unset=True)
    
    # Convert privacy classification if provided
    if "privacy_classification" in updates:
        try:
            updates["privacy_classification"] = PrivacyClassification(updates["privacy_classification"])
        except ValueError:
            raise HTTPException(400, f"Invalid privacy classification")
    
    dep = manager.update_dep(dep_id, actor=actor, **updates)
    
    if not dep:
        raise HTTPException(404, f"DEP not found: {dep_id}")
    
    return {"success": True, "dep": dep.to_dict()}


@router.delete("/deps/{dep_id}")
async def delete_dep(dep_id: str, actor: str = Query(...)):
    """Delete a DEP."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    success = manager.delete_dep(dep_id, actor=actor)
    
    if not success:
        raise HTTPException(404, f"DEP not found: {dep_id}")
    
    return {"success": True}


# --- Workflow Endpoints ---

@router.post("/deps/{dep_id}/submit")
async def submit_dep_for_review(dep_id: str, actor: str = Query(...)):
    """Submit a DEP for approval review."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    dep = manager.submit_for_review(dep_id, actor=actor)
    
    if not dep:
        raise HTTPException(400, f"Cannot submit DEP {dep_id} for review")
    
    return {"success": True, "dep": dep.to_dict()}


@router.post("/deps/{dep_id}/approve")
async def approve_dep(dep_id: str, request: ApprovalRequest):
    """Approve a DEP."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    dep = manager.approve_dep(
        dep_id,
        approver=request.approver,
        expires_days=request.expires_days,
    )
    
    if not dep:
        raise HTTPException(400, f"Cannot approve DEP {dep_id}")
    
    return {"success": True, "dep": dep.to_dict()}


@router.post("/deps/{dep_id}/reject")
async def reject_dep(dep_id: str, request: RejectionRequest):
    """Reject a DEP."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    dep = manager.reject_dep(
        dep_id,
        approver=request.approver,
        reason=request.reason,
    )
    
    if not dep:
        raise HTTPException(400, f"Cannot reject DEP {dep_id}")
    
    return {"success": True, "dep": dep.to_dict()}


# --- Templates and Utilities ---

@router.get("/templates")
async def list_templates():
    """List available DEP templates."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    
    return {
        "templates": {
            "standard": manager.get_template("standard"),
            "pii": manager.get_template("pii"),
            "process_mining": manager.get_template("process_mining"),
        }
    }


@router.get("/templates/{template_type}")
async def get_template(template_type: str):
    """Get a specific DEP template."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    template = manager.get_template(template_type)
    
    return {"template": template}


# --- Audit Endpoints ---

@router.get("/audit")
async def get_audit_log(
    dep_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
):
    """Get audit log entries."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    entries = manager.get_audit_log(dep_id=dep_id, limit=limit)
    
    return {
        "count": len(entries),
        "entries": entries,
    }


# --- Compliance Endpoints ---

@router.get("/compliance/summary/{tenant_id}")
async def get_compliance_summary(tenant_id: str):
    """Get compliance summary for a tenant."""
    from mithrillog.governance.dep_manager import get_dep_manager
    
    manager = get_dep_manager()
    
    # Check for expired DEPs
    manager.check_expired()
    
    return manager.get_compliance_summary(tenant_id)


@router.post("/compliance/check")
async def check_compliance(request: ComplianceCheckRequest):
    """Check text for PII and compliance violations."""
    from mithrillog.governance.compliance import get_compliance_checker, PIIType
    
    checker = get_compliance_checker()
    
    allowed = None
    if request.allowed_pii_types:
        try:
            allowed = {PIIType(t) for t in request.allowed_pii_types}
        except ValueError as e:
            raise HTTPException(400, f"Invalid PII type: {e}")
    
    return checker.validate_compliance(
        text=request.text,
        max_pii_count=request.max_pii_count,
        allowed_pii_types=allowed,
    )


@router.post("/compliance/classify")
async def classify_text(text: str = Query(...)):
    """Classify text by privacy sensitivity."""
    from mithrillog.governance.compliance import get_compliance_checker
    
    checker = get_compliance_checker()
    return checker.classify_text(text)


@router.post("/compliance/mask")
async def mask_pii(text: str = Query(...)):
    """Mask PII in text."""
    from mithrillog.governance.compliance import get_compliance_checker
    
    checker = get_compliance_checker()
    masked, matches = checker.mask_pii(text)
    
    return {
        "original_length": len(text),
        "masked_text": masked,
        "pii_count": len(matches),
        "pii_types": list(set(m.pii_type.value for m in matches)),
    }


@router.post("/compliance/scan-logs")
async def scan_logs(request: LogScanRequest):
    """Scan logs for PII."""
    from mithrillog.governance.compliance import get_compliance_checker
    
    checker = get_compliance_checker()
    return checker.scan_logs(request.logs)
