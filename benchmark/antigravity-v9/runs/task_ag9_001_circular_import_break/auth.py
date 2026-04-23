from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from user import User

def check_permission(user: User):
    # Added type hint for User using TYPE_CHECKING to avoid circular import
    return True
