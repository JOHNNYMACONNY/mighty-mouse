"""Adapter shim for protocol adherence delegating to mighty_mouse.verifier.adherence."""

from mighty_mouse.verifier.adherence import check_adherence

__all__ = ["check_adherence"]
