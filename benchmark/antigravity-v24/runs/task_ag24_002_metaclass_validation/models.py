class ValidatorMeta(type):
    def __new__(cls, name, bases, attrs):
        if name != 'PluginBase' and 'validate' not in attrs:
            raise TypeError(f'Missing validate method in {name}')
        return super().__new__(cls, name, bases, attrs)
class PluginBase(metaclass=ValidatorMeta): pass