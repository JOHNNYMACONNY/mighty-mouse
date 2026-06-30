"""Provider-agnostic project verification."""

from .core import CheckResult, VerificationResult, verify
from .detect import detect_projects

__all__ = ["CheckResult", "VerificationResult", "detect_projects", "verify"]
