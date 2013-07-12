class TransientModel(object):
    
    @classmethod
    def kind(cls):
        return cls.__name__
    
    @classmethod
    def required_fields(cls):
        return tuple()
    
    @classmethod
    def optional_fields(cls):
        return tuple()
    
    @classmethod
    def fields(cls):
        return cls.required_fields() + cls.optional_fields()
    
    def __init__(self, **kwargs):
        for prop in self.fields():
            setattr(self, prop, kwargs.get(prop))
            if prop in self.required_fields() and getattr(self, prop) is None:
                raise AttributeError, 'The property: %s is required.' % prop
    
    def properties(self):
        return dict([ ( prop, getattr(self, prop) ) for prop in self.fields() ])
