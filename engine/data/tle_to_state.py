import numpy as np
from sgp4.api import Satrec, jday
import datetime

def tle_to_state(tle1, tle2, epoch=None):
    """
    Convert TLE to ECI position & velocity (meters, m/s)
    """
    sat = Satrec.twoline2rv(tle1, tle2)

    if epoch is None:
        now = datetime.datetime.utcnow()
    else:
        now = epoch

    jd, fr = jday(
        now.year, now.month, now.day,
        now.hour, now.minute, now.second
    )

    e, r, v = sat.sgp4(jd, fr)

    if e != 0:
        raise RuntimeError("SGP4 propagation failed")

    r = np.array(r) * 1000.0      # km → m
    v = np.array(v) * 1000.0      # km/s → m/s

    return r, v
