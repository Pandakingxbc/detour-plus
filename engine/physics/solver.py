# src/physics/solver.py
import numpy as np
from engine.physics.state import State

class RK4Solver:
    """
    Runge-Kutta 4th order solver for state integration.
    """
    def __init__(self, force_model):
        self.force = force_model

    def step(self, state, dt):
        """
        Perform a single RK4 step.
        """
        def deriv(s):
            a = self.force.acceleration(s)
            return np.hstack((s.v, a))

        y0 = np.hstack((state.r, state.v))

        k1 = deriv(state)
        k2_state = State(y0[:3] + 0.5 * dt * k1[:3], y0[3:] + 0.5 * dt * k1[3:])
        k2 = deriv(k2_state)
        k3_state = State(y0[:3] + 0.5 * dt * k2[:3], y0[3:] + 0.5 * dt * k2[3:])
        k3 = deriv(k3_state)
        k4_state = State(y0[:3] + dt * k3[:3], y0[3:] + dt * k3[3:])
        k4 = deriv(k4_state)

        y_next = y0 + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

        return State(y_next[:3], y_next[3:])