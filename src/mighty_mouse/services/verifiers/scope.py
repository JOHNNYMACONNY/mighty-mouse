"""Adapter shim for task scope verification delegating to mighty_mouse.verifier.scope."""

from mighty_mouse.verifier.scope import check_scope, verify_task_scope, verify_task_scope as verify

__all__ = ["check_scope", "verify_task_scope", "verify"]
