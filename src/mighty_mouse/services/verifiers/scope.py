"""Adapter shim for task scope verification delegating to mighty_mouse.verifier.scope."""

from mighty_mouse.verifier.scope import verify_task_scope as verify

__all__ = ["verify"]
