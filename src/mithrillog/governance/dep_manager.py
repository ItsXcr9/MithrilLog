"""
Data Enablement Plan (DEP) Manager

Manages data governance plans for datasets including:
- Privacy classification
- Security requirements
- Data handling procedures
- Approval workflows
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mithrillog.governance.dep_manager")


class DEPStatus(str, Enum):
    """Status of a Data Enablement Plan."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class PrivacyClassification(str, Enum):
    """Privacy classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    SENSITIVE_PII = "sensitive_pii"


@dataclass
class DataEnablementPlan:
    """A Data Enablement Plan document."""
    id: str
    tenant_id: str
    name: str
    description: str
    status: DEPStatus = DEPStatus.DRAFT
    
    # Data classification
    privacy_classification: PrivacyClassification = PrivacyClassification.INTERNAL
    data_source: str = ""
    data_elements: List[str] = field(default_factory=list)
    
    # Security requirements
    encryption_required: bool = True
    access_controls: List[str] = field(default_factory=list)
    retention_days: int = 90
    
    # Handling procedures
    data_handling_notes: str = ""
    masking_rules: Dict[str, str] = field(default_factory=dict)  # {field: rule}
    
    # Approval workflow
    owner: str = ""
    approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "privacy_classification": self.privacy_classification.value,
            "data_source": self.data_source,
            "data_elements": self.data_elements,
            "encryption_required": self.encryption_required,
            "access_controls": self.access_controls,
            "retention_days": self.retention_days,
            "data_handling_notes": self.data_handling_notes,
            "masking_rules": self.masking_rules,
            "owner": self.owner,
            "approver": self.approver,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataEnablementPlan":
        return cls(
            id=data["id"],
            tenant_id=data["tenant_id"],
            name=data["name"],
            description=data.get("description", ""),
            status=DEPStatus(data.get("status", "draft")),
            privacy_classification=PrivacyClassification(data.get("privacy_classification", "internal")),
            data_source=data.get("data_source", ""),
            data_elements=data.get("data_elements", []),
            encryption_required=data.get("encryption_required", True),
            access_controls=data.get("access_controls", []),
            retention_days=data.get("retention_days", 90),
            data_handling_notes=data.get("data_handling_notes", ""),
            masking_rules=data.get("masking_rules", {}),
            owner=data.get("owner", ""),
            approver=data.get("approver"),
            approved_at=datetime.fromisoformat(data["approved_at"]) if data.get("approved_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
        )


class DEPManager:
    """
    Manages Data Enablement Plans for governance compliance.
    
    Features:
    - CRUD operations for DEPs
    - Approval workflow management
    - Expiration tracking
    - Template generation
    """
    
    def __init__(self, storage_path: str = "data/governance"):
        self.storage_path = storage_path
        self._deps: Dict[str, DataEnablementPlan] = {}
        self._audit_log: List[Dict[str, Any]] = []
    
    def create_dep(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        owner: str = "",
        **kwargs,
    ) -> DataEnablementPlan:
        """Create a new Data Enablement Plan."""
        dep_id = str(uuid.uuid4())
        
        dep = DataEnablementPlan(
            id=dep_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            owner=owner,
            **kwargs,
        )
        
        self._deps[dep_id] = dep
        self._audit("create", dep_id, tenant_id, owner)
        
        logger.info(f"Created DEP: {name} ({dep_id}) for tenant {tenant_id}")
        return dep
    
    def get_dep(self, dep_id: str) -> Optional[DataEnablementPlan]:
        """Get a DEP by ID."""
        return self._deps.get(dep_id)
    
    def list_deps(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[DEPStatus] = None,
    ) -> List[DataEnablementPlan]:
        """List DEPs with optional filtering."""
        result = list(self._deps.values())
        
        if tenant_id:
            result = [d for d in result if d.tenant_id == tenant_id]
        
        if status:
            result = [d for d in result if d.status == status]
        
        return sorted(result, key=lambda d: d.updated_at, reverse=True)
    
    def update_dep(
        self,
        dep_id: str,
        actor: str,
        **updates,
    ) -> Optional[DataEnablementPlan]:
        """Update a DEP."""
        dep = self._deps.get(dep_id)
        if not dep:
            return None
        
        for key, value in updates.items():
            if hasattr(dep, key) and key not in ("id", "tenant_id", "created_at"):
                setattr(dep, key, value)
        
        dep.updated_at = datetime.utcnow()
        self._audit("update", dep_id, dep.tenant_id, actor, updates)
        
        logger.info(f"Updated DEP: {dep_id}")
        return dep
    
    def submit_for_review(self, dep_id: str, actor: str) -> Optional[DataEnablementPlan]:
        """Submit a DEP for approval review."""
        dep = self._deps.get(dep_id)
        if not dep:
            return None
        
        if dep.status != DEPStatus.DRAFT:
            logger.warning(f"Cannot submit DEP {dep_id}: status is {dep.status}")
            return None
        
        dep.status = DEPStatus.PENDING_REVIEW
        dep.updated_at = datetime.utcnow()
        self._audit("submit_review", dep_id, dep.tenant_id, actor)
        
        logger.info(f"DEP {dep_id} submitted for review")
        return dep
    
    def approve_dep(
        self,
        dep_id: str,
        approver: str,
        expires_days: int = 365,
    ) -> Optional[DataEnablementPlan]:
        """Approve a DEP."""
        dep = self._deps.get(dep_id)
        if not dep:
            return None
        
        if dep.status != DEPStatus.PENDING_REVIEW:
            logger.warning(f"Cannot approve DEP {dep_id}: status is {dep.status}")
            return None
        
        from datetime import timedelta
        
        dep.status = DEPStatus.APPROVED
        dep.approver = approver
        dep.approved_at = datetime.utcnow()
        dep.expires_at = datetime.utcnow() + timedelta(days=expires_days)
        dep.updated_at = datetime.utcnow()
        
        self._audit("approve", dep_id, dep.tenant_id, approver)
        
        logger.info(f"DEP {dep_id} approved by {approver}")
        return dep
    
    def reject_dep(
        self,
        dep_id: str,
        approver: str,
        reason: str = "",
    ) -> Optional[DataEnablementPlan]:
        """Reject a DEP."""
        dep = self._deps.get(dep_id)
        if not dep:
            return None
        
        dep.status = DEPStatus.REJECTED
        dep.approver = approver
        dep.data_handling_notes += f"\n\nRejection reason: {reason}"
        dep.updated_at = datetime.utcnow()
        
        self._audit("reject", dep_id, dep.tenant_id, approver, {"reason": reason})
        
        logger.info(f"DEP {dep_id} rejected by {approver}: {reason}")
        return dep
    
    def delete_dep(self, dep_id: str, actor: str) -> bool:
        """Delete a DEP."""
        dep = self._deps.get(dep_id)
        if not dep:
            return False
        
        self._audit("delete", dep_id, dep.tenant_id, actor)
        del self._deps[dep_id]
        
        logger.info(f"DEP {dep_id} deleted by {actor}")
        return True
    
    def get_template(self, template_type: str = "standard") -> Dict[str, Any]:
        """Get a DEP template."""
        templates = {
            "standard": {
                "name": "Standard Dataset DEP",
                "description": "Template for standard internal datasets",
                "privacy_classification": "internal",
                "encryption_required": True,
                "retention_days": 90,
                "access_controls": ["role:analyst", "role:engineer"],
                "masking_rules": {},
            },
            "pii": {
                "name": "PII Dataset DEP",
                "description": "Template for datasets containing PII",
                "privacy_classification": "pii",
                "encryption_required": True,
                "retention_days": 30,
                "access_controls": ["role:data_steward"],
                "masking_rules": {
                    "email": "hash",
                    "phone": "mask",
                    "ssn": "redact",
                },
            },
            "process_mining": {
                "name": "Process Mining Dataset DEP",
                "description": "Template for process mining event logs",
                "privacy_classification": "internal",
                "encryption_required": True,
                "retention_days": 365,
                "access_controls": ["role:process_analyst", "role:data_engineer"],
                "masking_rules": {
                    "user_id": "pseudonymize",
                },
            },
        }
        
        return templates.get(template_type, templates["standard"])
    
    def get_audit_log(
        self,
        dep_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        entries = self._audit_log
        
        if dep_id:
            entries = [e for e in entries if e["dep_id"] == dep_id]
        
        return entries[-limit:]
    
    def _audit(
        self,
        action: str,
        dep_id: str,
        tenant_id: str,
        actor: str,
        details: Dict[str, Any] = None,
    ):
        """Record an audit log entry."""
        self._audit_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "dep_id": dep_id,
            "tenant_id": tenant_id,
            "actor": actor,
            "details": details or {},
        })
        
        # Keep last 10000 entries
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-10000:]
    
    def check_expired(self) -> List[DataEnablementPlan]:
        """Check and mark expired DEPs."""
        now = datetime.utcnow()
        expired = []
        
        for dep in self._deps.values():
            if dep.status == DEPStatus.APPROVED and dep.expires_at and dep.expires_at < now:
                dep.status = DEPStatus.EXPIRED
                dep.updated_at = now
                self._audit("expire", dep.id, dep.tenant_id, "system")
                expired.append(dep)
                logger.info(f"DEP {dep.id} expired")
        
        return expired
    
    def get_compliance_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get compliance summary for a tenant."""
        deps = self.list_deps(tenant_id=tenant_id)
        
        by_status = {}
        for dep in deps:
            status = dep.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        by_classification = {}
        for dep in deps:
            classification = dep.privacy_classification.value
            by_classification[classification] = by_classification.get(classification, 0) + 1
        
        # Check for issues
        issues = []
        for dep in deps:
            if dep.status == DEPStatus.EXPIRED:
                issues.append(f"DEP '{dep.name}' has expired")
            if dep.status == DEPStatus.APPROVED and dep.expires_at:
                days_until = (dep.expires_at - datetime.utcnow()).days
                if days_until < 30:
                    issues.append(f"DEP '{dep.name}' expires in {days_until} days")
        
        return {
            "tenant_id": tenant_id,
            "total_deps": len(deps),
            "by_status": by_status,
            "by_classification": by_classification,
            "issues": issues,
            "compliant": len(issues) == 0,
        }


# Singleton instance
_dep_manager: Optional[DEPManager] = None


def get_dep_manager() -> DEPManager:
    """Get or create the singleton DEPManager instance."""
    global _dep_manager
    if _dep_manager is None:
        _dep_manager = DEPManager()
    return _dep_manager
