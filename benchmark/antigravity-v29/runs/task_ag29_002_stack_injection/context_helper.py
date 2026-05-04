import sys

def get_context_var(var_name):
    # Accessing the execution frame of the caller (depth 1)
    # This allows us to introspect local variables defined in the calling scope
    try:
        # frame 0 is this function, frame 1 is the immediate caller
        caller_frame = sys._getframe(1)
        
        # Searching the caller's local symbol table
        if var_name in caller_frame.f_locals:
            return caller_frame.f_locals[var_name]
            
        # Fallback: Check globals if not in locals?
        # The requirement specifically says "Search the caller's local variables"
        raise LookupError(f"Context variable '{var_name}' not found in caller scope")
    except (ValueError, AttributeError):
        # Frame access might be restricted or unavailable
        raise LookupError(f"Unable to access caller stack frame for '{var_name}'")
