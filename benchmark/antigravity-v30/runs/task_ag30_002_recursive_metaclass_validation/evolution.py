class EvolutionMeta(type):
    # Metaclass that enforces strict method implementation across the entire inheritance tree
    def __new__(cls, name, bases, attrs):
        # We skip validation for the root base class
        if name != 'PluginBase':
            # Strictly requiring the 'run' method to be defined in the current class definition
            # This prevents silent inheritance of old behavior and forces explicit lifecycle management
            if 'run' not in attrs:
                raise TypeError("Missing run method")
                
        return super().__new__(cls, name, bases, attrs)

class PluginBase(metaclass=EvolutionMeta):
    # The foundation for all evolving plugins
    pass
