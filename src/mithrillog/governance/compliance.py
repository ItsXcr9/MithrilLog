"""
Compliance Checker

PII detection and data compliance enforcement:
- Regex-based PII patterns
- Masking and redaction
- Compliance rule validation
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("mithrillog.governance.compliance")


class PIIType(str, Enum):
    """Types of PII detected."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    API_KEY = "api_key"
    PASSWORD = "password"
    JWT = "jwt"
    AWS_KEY = "aws_key"
    NAME = "name"


@dataclass
class PIIMatch:
    """A detected PII instance."""
    pii_type: PIIType
    original: str
    masked: str
    start_pos: int
    end_pos: int
    confidence: float


class ComplianceChecker:
    """
    Check and enforce data compliance rules.
    
    Features:
    - PII detection with regex patterns
    - Automatic masking/redaction
    - Compliance rule validation
    """
    
    # PII detection patterns
    PATTERNS = {
        PIIType.EMAIL: (
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            0.95
        ),
        PIIType.PHONE: (
            r'\b(?:\+?1[-.\s]?)?(?:\(?[0-9]{3}\)?[-.\s]?)?[0-9]{3}[-.\s]?[0-9]{4}\b',
            0.8
        ),
        PIIType.SSN: (
            r'\b[0-9]{3}[-\s]?[0-9]{2}[-\s]?[0-9]{4}\b',
            0.9
        ),
        PIIType.CREDIT_CARD: (
            r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
            0.95
        ),
        PIIType.IP_ADDRESS: (
            r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            0.7
        ),
        PIIType.API_KEY: (
            r'\b(?:api[_-]?key|apikey|api_secret)[=:\s]+["\']?([a-zA-Z0-9_-]{20,})["\']?',
            0.9
        ),
        PIIType.PASSWORD: (
            r'(?:password|passwd|pwd)[=:\s]+["\']?([^\s"\']{8,})["\']?',
            0.85
        ),
        PIIType.JWT: (
            r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',
            0.95
        ),
        PIIType.AWS_KEY: (
            r'\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b',
            0.95
        ),
    }
    
    def __init__(self, enabled_types: Optional[Set[PIIType]] = None):
        """
        Initialize compliance checker.
        
        Args:
            enabled_types: Set of PII types to detect. If None, detect all.
        """
        self.enabled_types = enabled_types or set(PIIType)
        self._compiled_patterns = {}
        
        for pii_type, (pattern, _) in self.PATTERNS.items():
            if pii_type in self.enabled_types:
                self._compiled_patterns[pii_type] = re.compile(pattern, re.IGNORECASE)
    
    def detect_pii(self, text: str) -> List[PIIMatch]:
        """
        Detect PII in text.
        
        Returns list of PII matches with type, location, and confidence.
        """
        matches = []
        
        for pii_type, pattern in self._compiled_patterns.items():
            _, confidence = self.PATTERNS[pii_type]
            
            for match in pattern.finditer(text):
                original = match.group(0)
                masked = self._mask_value(pii_type, original)
                
                matches.append(PIIMatch(
                    pii_type=pii_type,
                    original=original,
                    masked=masked,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=confidence,
                ))
        
        return matches
    
    def mask_pii(self, text: str) -> Tuple[str, List[PIIMatch]]:
        """
        Mask all PII in text.
        
        Returns (masked_text, list of matches).
        """
        matches = self.detect_pii(text)
        
        # Sort by position (reverse) to replace from end to start
        matches.sort(key=lambda m: m.start_pos, reverse=True)
        
        result = text
        for match in matches:
            result = result[:match.start_pos] + match.masked + result[match.end_pos:]
        
        return result, matches
    
    def redact_pii(self, text: str) -> str:
        """Fully redact all PII in text."""
        matches = self.detect_pii(text)
        matches.sort(key=lambda m: m.start_pos, reverse=True)
        
        result = text
        for match in matches:
            result = result[:match.start_pos] + "[REDACTED]" + result[match.end_pos:]
        
        return result
    
    def _mask_value(self, pii_type: PIIType, value: str) -> str:
        """Apply appropriate masking for PII type."""
        if pii_type == PIIType.EMAIL:
            parts = value.split("@")
            if len(parts) == 2:
                local = parts[0]
                masked_local = local[0] + "*" * min(len(local) - 1, 5) if len(local) > 1 else "*"
                return f"{masked_local}@{parts[1]}"
        
        elif pii_type == PIIType.PHONE:
            # Keep last 4 digits
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 4:
                return "***-***-" + digits[-4:]
        
        elif pii_type == PIIType.SSN:
            return "***-**-" + value[-4:] if len(value) >= 4 else "***-**-****"
        
        elif pii_type == PIIType.CREDIT_CARD:
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 4:
                return "*" * (len(digits) - 4) + digits[-4:]
        
        elif pii_type == PIIType.IP_ADDRESS:
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.***.***"
        
        elif pii_type in (PIIType.API_KEY, PIIType.PASSWORD, PIIType.JWT, PIIType.AWS_KEY):
            if len(value) > 6:
                return value[:3] + "*" * (len(value) - 6) + value[-3:]
        
        # Default masking
        return "*" * len(value)
    
    def classify_text(self, text: str) -> Dict[str, Any]:
        """
        Classify text by privacy sensitivity.
        
        Returns classification with detected PII types.
        """
        matches = self.detect_pii(text)
        
        pii_types = set(m.pii_type for m in matches)
        
        # Determine classification
        if PIIType.SSN in pii_types or PIIType.CREDIT_CARD in pii_types:
            classification = "sensitive_pii"
            risk_level = "critical"
        elif PIIType.EMAIL in pii_types or PIIType.PHONE in pii_types:
            classification = "pii"
            risk_level = "high"
        elif PIIType.API_KEY in pii_types or PIIType.PASSWORD in pii_types:
            classification = "confidential"
            risk_level = "high"
        elif PIIType.IP_ADDRESS in pii_types:
            classification = "internal"
            risk_level = "medium"
        else:
            classification = "public"
            risk_level = "low"
        
        return {
            "classification": classification,
            "risk_level": risk_level,
            "pii_detected": len(matches) > 0,
            "pii_count": len(matches),
            "pii_types": [t.value for t in pii_types],
            "matches": [
                {
                    "type": m.pii_type.value,
                    "masked": m.masked,
                    "confidence": m.confidence,
                }
                for m in matches
            ],
        }
    
    def validate_compliance(
        self,
        text: str,
        max_pii_count: int = 0,
        allowed_pii_types: Optional[Set[PIIType]] = None,
    ) -> Dict[str, Any]:
        """
        Validate text against compliance rules.
        
        Returns validation result with any violations.
        """
        matches = self.detect_pii(text)
        
        violations = []
        
        if len(matches) > max_pii_count:
            violations.append({
                "rule": "max_pii_count",
                "expected": max_pii_count,
                "actual": len(matches),
                "message": f"Found {len(matches)} PII instances, max allowed is {max_pii_count}",
            })
        
        if allowed_pii_types is not None:
            disallowed = [m for m in matches if m.pii_type not in allowed_pii_types]
            if disallowed:
                violations.append({
                    "rule": "allowed_pii_types",
                    "expected": [t.value for t in allowed_pii_types],
                    "actual": list(set(m.pii_type.value for m in disallowed)),
                    "message": f"Found disallowed PII types: {[m.pii_type.value for m in disallowed]}",
                })
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "pii_count": len(matches),
        }
    
    def scan_logs(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Scan a batch of logs for PII.
        
        Returns summary with affected log indices.
        """
        affected_logs = []
        total_pii = 0
        pii_by_type = {}
        
        for i, log in enumerate(logs):
            message = log.get("message", "")
            matches = self.detect_pii(message)
            
            if matches:
                affected_logs.append({
                    "index": i,
                    "pii_count": len(matches),
                    "pii_types": list(set(m.pii_type.value for m in matches)),
                })
                total_pii += len(matches)
                
                for m in matches:
                    pii_by_type[m.pii_type.value] = pii_by_type.get(m.pii_type.value, 0) + 1
        
        return {
            "logs_scanned": len(logs),
            "logs_with_pii": len(affected_logs),
            "total_pii_instances": total_pii,
            "pii_by_type": pii_by_type,
            "affected_logs": affected_logs[:100],  # Limit output
            "truncated": len(affected_logs) > 100,
        }


# Singleton instance
_compliance_checker: Optional[ComplianceChecker] = None


def get_compliance_checker() -> ComplianceChecker:
    """Get or create the singleton ComplianceChecker instance."""
    global _compliance_checker
    if _compliance_checker is None:
        _compliance_checker = ComplianceChecker()
    return _compliance_checker
