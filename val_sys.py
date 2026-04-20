class Validator:
    def __init__(self, rs): self.rs = rs
    def validate(self, d): return all(r(d) for r in self.rs)