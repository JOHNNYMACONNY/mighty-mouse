class TrafficLight:
    """A state machine for a traffic light with a subtle bug."""
    STATES = ["red", "green", "yellow"]

    def __init__(self):
        self.state = "red"

    def advance(self):
        # BUG: index logic is off-by-one when wrapping
        idx = self.STATES.index(self.state)
        self.state = self.STATES[(idx + 1) % len(self.STATES)]

    def get_state(self):
        return self.state
