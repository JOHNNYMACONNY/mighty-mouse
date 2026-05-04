# validators.py
import functools

# The "Hidden" rule: Every field in a decorated class must be listed in 
# the __annotations__ dict, or the validator will reject it at runtime.

def enforce_strict_types(cls):
    orig_init = cls.__init__
    
    @functools.wraps(orig_init)
    def new_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        # Audit: check if all instance vars have annotations
        for attr in self.__dict__:
            if attr not in cls.__annotations__:
                raise TypeError(f"Attribute '{attr}' in {cls.__name__} is missing a type annotation! Mandatory for strict validation.")
    
    cls.__init__ = new_init
    return cls
