# src/physics/state.py
import numpy as np

class State:
    """
    State vector for orbital motion in 3D.
    [x, y, z, vx, vy, vz]
    """
    def __init__(self, position, velocity):
        if len(position) != 3 or len(velocity) != 3:
            raise ValueError("Position and velocity must be 3D vectors.")
        self.r = np.array(position, dtype=float)
        self.v = np.array(velocity, dtype=float)

    def copy(self):
        return State(self.r.copy(), self.v.copy())