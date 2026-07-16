class MigrationStep:

    def __init__(self, name, forward_fn, rollback_fn):
        self.name = name
        self.forward_fn = forward_fn
        self.rollback_fn = rollback_fn


class Migration:

    def __init__(self, steps):
        self.steps = steps
        self.applied_steps = []

    def apply(self, state):
        # Bug: Does not rollback already applied steps when a step fails!
        for step in self.steps:
            step.forward_fn(state)
            self.applied_steps.append(step)
