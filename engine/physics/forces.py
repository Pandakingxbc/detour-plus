
import numpy as np
from engine.config.settings import GM, RE, J2, atmospheric_density
from engine.physics.ephemeris import sun_position
from engine.physics.third_body import third_body_accel_from_positions, MU_SUN, MU_MOON

# Additional harmonics (example values — replace with authoritative model if desired)
J3 = -2.532153e-6
J4 = -1.6109876e-6

# Solar constants
P_SOLAR = 4.56e-6  # N/m^2 at 1 AU
AU = 1.495978707e11  # meters

class ForceModel:
    """
    Base force model. Acceleration signature accepts optional time t (seconds).
    """
    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        raise NotImplementedError


class NewtonianGravity(ForceModel):
    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        r = state.r
        norm = np.linalg.norm(r)
        if norm == 0:
            return np.zeros(3, dtype=float)
        return -(GM / norm**3) * r


class J2Perturbation(ForceModel):
    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        r = state.r
        norm = np.linalg.norm(r)
        if norm == 0:
            return np.zeros(3, dtype=float)
        mu = GM
        z_r = r[2] / norm
        z2_r2 = z_r**2
        factor = -(3.0 / 2.0) * J2 * (mu * (RE**2) / (norm**5))
        a_j2 = factor * np.array([
            r[0] * (5.0 * z2_r2 - 1.0),
            r[1] * (5.0 * z2_r2 - 1.0),
            r[2] * (5.0 * z2_r2 - 3.0)
        ], dtype=float)
        return a_j2


class J3Perturbation(ForceModel):
    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        r = state.r
        norm = np.linalg.norm(r)
        if norm == 0:
            return np.zeros(3, dtype=float)
        x, y, z = r
        mu = GM
        Re = RE
        zr = z / norm
        zr2 = zr * zr
        # Derived approximate J3 acceleration (zonal)
        factor = -0.5 * J3 * mu * Re**3 / norm**7
        ax = factor * x * (5.0 * zr * (7.0 * zr2 - 3.0))
        ay = factor * y * (5.0 * zr * (7.0 * zr2 - 3.0))
        az = factor * (3.0 - 30.0 * zr2 + 35.0 * zr2 * zr2)
        return np.array([ax, ay, az], dtype=float)


class J4Perturbation(ForceModel):
    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        r = state.r
        norm = np.linalg.norm(r)
        if norm == 0:
            return np.zeros(3, dtype=float)
        x, y, z = r
        mu = GM
        Re = RE
        zr = z / norm
        zr2 = zr * zr
        # approximate J4 zonal acceleration
        factor = (5.0 / 8.0) * J4 * mu * Re**4 / norm**9
        common = (35.0 * zr2 * zr2 - 30.0 * zr2 + 3.0)
        ax = factor * x * common
        ay = factor * y * common
        az = factor * z * (35.0 * zr2 * zr2 - 42.0 * zr2 + 9.0)
        return np.array([ax, ay, az], dtype=float)


class AtmosphericDrag(ForceModel):
    def __init__(self, ballistic_coeff: float):
        self.B = float(ballistic_coeff)

    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        position = state.r
        velocity = state.v
        v = np.linalg.norm(velocity)
        if v == 0.0:
            return np.zeros(3, dtype=float)
        altitude = np.linalg.norm(position) - RE
        rho = atmospheric_density(altitude)
        if rho == 0.0:
            return np.zeros(3, dtype=float)
        a_mag = -0.5 * rho * (1.0 / self.B) * v**2
        unit_v = velocity / v
        return a_mag * unit_v


class SolarRadiationPressure(ForceModel):
    def __init__(self, Cr: float = 1.2, area_mass_ratio: float = 0.02):
        self.Cr = float(Cr)
        self.Am = float(area_mass_ratio)  # A/m

    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        # Sun position (approx)
        r_sc = state.r
        r_sun = sun_position(t)
        vec = r_sc - r_sun  # vector from Sun -> spacecraft
        d = np.linalg.norm(vec)
        if d == 0.0:
            return np.zeros(3, dtype=float)
        # inverse square scaling relative to 1 AU
        a_mag = (P_SOLAR * self.Cr * self.Am) * (AU / d)**2
        return a_mag * (vec / d)


class ThirdBodyForce(ForceModel):
    def __init__(self, include_sun: bool = True, include_moon: bool = True):
        self.include_sun = bool(include_sun)
        self.include_moon = bool(include_moon)

    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        total = np.zeros(3, dtype=float)
        r_sc = state.r
        if self.include_sun:
            r_sun = sun_position(t)
            total += third_body_accel_from_positions(r_sc, r_sun, MU_SUN)
        if self.include_moon:
            r_moon = sun_position(t)  # careful: replace below with moon_position if available
            # For safety, call third_body functions using ephemeris; but if moon ephemeris not imported, set zero.
            # We'll prefer to import moon_position in engine integration and add Moon acceleration externally if needed.
        return total


class CompositeForce(ForceModel):
    def __init__(self, *models):
        self.models = list(models)

    def acceleration(self, state, t: float = 0.0) -> np.ndarray:
        total_a = np.zeros(3, dtype=float)
        for model in self.models:
            # allow models to accept (state, t) signature
            try:
                total_a += model.acceleration(state, t)
            except TypeError:
                # fallback if model expects (state) only
                total_a += model.acceleration(state)
        return total_a

    def has_drag(self) -> bool:
        return any(isinstance(m, AtmosphericDrag) for m in self.models)
