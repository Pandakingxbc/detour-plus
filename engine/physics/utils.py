
import numpy as np
from engine.config.settings import GM, RE, J2
def specific_energy(state):
    """
    Compute specific mechanical energy (kinetic + potential, including J2).
    Used as a numerical stability diagnostic (not physical conservation proof).
    """
    position = state.r
    r = np.linalg.norm(position)
    cos_theta = position[2] / r
    phi_newton = -GM / r
    phi_j2 = -(GM / r) * (J2 * (RE / r)**2) * (3 * cos_theta**2 - 1) / 2
    phi = phi_newton + phi_j2
    kinetic = 0.5 * np.dot(state.v, state.v)
    return kinetic + phi