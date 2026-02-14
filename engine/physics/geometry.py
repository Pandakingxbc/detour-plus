import numpy as np

def time_of_closest_approach(r1, v1, r2, v2):
    """
    Analytical time-of-closest-approach (TCA) for two objects with linear relative motion.
    Inputs:
        r1, v1, r2, v2 : numpy arrays (2D or 3D) positions (m) and velocities (m/s)
    Returns:
        tca (seconds, scalar) - time from current epoch to closest approach (can be negative)
        miss_distance (meters) - distance at TCA
    Note: This assumes straight-line motion during the short TCA window (valid for screening).
    """
    r1 = np.array(r1, dtype=float)
    v1 = np.array(v1, dtype=float)
    r2 = np.array(r2, dtype=float)
    v2 = np.array(v2, dtype=float)

    dr = r1 - r2
    dv = v1 - v2

    dv2 = np.dot(dv, dv)
    if dv2 == 0:
        # relative velocity zero => distance constant
        return 0.0, float(np.linalg.norm(dr))

    tca = - np.dot(dr, dv) / dv2
    # compute miss at tca
    miss_vec = dr + dv * tca
    miss = float(np.linalg.norm(miss_vec))
    return float(tca), miss
