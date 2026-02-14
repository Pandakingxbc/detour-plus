import numpy as np

# Dormand–Prince (7 stages) coefficients
_C = np.array([0.0, 1/5, 3/10, 4/5, 8/9, 1.0, 1.0], dtype=float)
_A = [
    [],
    [1/5],
    [3/40, 9/40],
    [44/45, -56/15, 32/9],
    [19372/6561, -25360/2187, 64448/6561, -212/729],
    [9017/3168, -355/33, 46732/5247, 49/176, -5103/18656],
    [35/384, 0.0, 500/1113, 125/192, -2187/6784, 11/84]
]
_B_HIGH = np.array([35/384, 0.0, 500/1113, 125/192, -2187/6784, 11/84, 0.0], dtype=float)
_B_LOW = np.array([5179/57600, 0.0, 7571/16695, 393/640, -92097/339200, 187/2100, 1/40], dtype=float)

class RK45Solver:
    """
    Dormand–Prince (RK45) adaptive integrator for orbital state integration.
    State object must have .r (3,) and .v (3,) numpy arrays.
    Force model must implement acceleration(state, t).
    """
    def __init__(self, force_model, rtol: float = 1e-9, atol: float = 1e-12, dt_min: float = 1e-6, dt_max: float = 100.0):
        self.force = force_model
        self.rtol = float(rtol)
        self.atol = float(atol)
        self.dt_min = float(dt_min)
        self.dt_max = float(dt_max)

    def _deriv(self, state):
        # returns concatenated derivative [vx, vy, vz, ax, ay, az]
        a = self.force.acceleration(state, self._t_current)
        return np.hstack((state.v, a))

    def step(self, state, dt: float, t0: float = 0.0):
        """
        Integrate from t0 to t0+dt and return new State-like object.
        Uses adaptive substepping to meet error tolerances.
        The input 'state' must support .r and .v and be constructible via same class:
            new_state = State(r_next, v_next)
        For compatibility with existing State class, we avoid direct dependency here.
        """
        dt = float(dt)
        if dt <= 0:
            return state
        t = float(t0)
        t_end = t0 + dt
        s = state
        self._t_current = t
        h = min(self.dt_max, t_end - t)
        while t < t_end - 1e-15:
            h = min(h, t_end - t)  # ensure no overshoot
            success = False
            while not success:
                # compute k stages
                ks = []
                # k1
                self._t_current = t + _C[0] * h
                k1 = self._deriv(s)
                ks.append(k1)
                # other stages
                for i in range(1, len(_C)):
                    ti = t + _C[i] * h
                    yi = np.hstack((s.r, s.v))
                    for j, aij in enumerate(_A[i]):
                        yi += h * aij * ks[j]
                    # create temp state for accel evaluation
                    r_tmp = yi[0:3]
                    v_tmp = yi[3:6]
                    class _TmpState:
                        pass
                    tmp = _TmpState()
                    tmp.r = r_tmp
                    tmp.v = v_tmp
                    self._t_current = ti
                    ki = self._deriv(tmp)
                    ks.append(ki)
                # combine to high and low order
                y0 = np.hstack((s.r, s.v))
                y_high = y0.copy()
                y_low = y0.copy()
                for i_k in range(len(ks)):
                    y_high += h * _B_HIGH[i_k] * ks[i_k]
                    y_low += h * _B_LOW[i_k] * ks[i_k]
                # error estimate
                err_vec = y_high - y_low
                # scaling for each component
                scale = self.atol + self.rtol * np.maximum(np.abs(y0), np.abs(y_high))
                # RMS error norm
                err_ratio = np.sqrt(np.mean((np.abs(err_vec) / scale) ** 2))
                if err_ratio <= 1.0:
                    # accept step
                    y_next = y_high
                    r_next = y_next[0:3]
                    v_next = y_next[3:6]
                    # create new State-like return (use original class)
                    try:
                        new_state = type(s)(r_next, v_next)
                    except Exception:
                        # fallback: create simple object with r/v
                        class _StateLike:
                            def __init__(self, r, v):
                                self.r = np.array(r, dtype=float)
                                self.v = np.array(v, dtype=float)
                        new_state = _StateLike(r_next, v_next)
                    s = new_state
                    t += h
                    success = True
                    # adapt step size for next
                    if err_ratio == 0.0:
                        factor = 5.0
                    else:
                        factor = 0.9 * (1.0 / err_ratio) ** 0.2
                    h = h * np.clip(factor, 0.2, 5.0)
                    h = min(max(h, self.dt_min), self.dt_max)
                else:
                    # reject & reduce step
                    if err_ratio == 0.0:
                        factor = 0.1
                    else:
                        factor = 0.9 * (1.0 / err_ratio) ** 0.25
                    h_new = h * max(0.1, factor)
                    if h_new < self.dt_min:
                        # cannot reduce further, accept to avoid stuck
                        y_next = y_high
                        r_next = y_next[0:3]
                        v_next = y_next[3:6]
                        try:
                            new_state = type(s)(r_next, v_next)
                        except Exception:
                            class _StateLike:
                                def __init__(self, r, v):
                                    self.r = np.array(r, dtype=float)
                                    self.v = np.array(v, dtype=float)
                            new_state = _StateLike(r_next, v_next)
                        s = new_state
                        t += h
                        success = True
                        h = self.dt_min  # for next
                    else:
                        h = max(self.dt_min, h_new)
                        # retry with smaller h
        return s

