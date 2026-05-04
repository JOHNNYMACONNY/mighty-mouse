class EvolutionMeta(type):
    def __new__(cls, name, bases, attrs):
        return super().__new__(cls, name, bases, attrs)

class PluginBase(metaclass=EvolutionMeta):
    pass
