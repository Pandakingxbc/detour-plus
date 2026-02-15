# Moving Satellite Visualization - Setup Guide

## What Was Changed

### Backend (3 files modified/created)

1. **`api/routes/satellite_demo.py`** (NEW)
   - Creates an endpoint `/api/satellite-demo/iss-trajectory`
   - Uses your `Satellite` class from `engine/models/satellite.py`
   - Propagates the satellite orbit over time (90 minutes default)
   - Returns trajectory data: times, positions, velocities

2. **`api/app.py`** (MODIFIED)
   - Added import for `satellite_demo` router
   - Registered the new endpoint in the FastAPI app

### Frontend (2 files modified/created)

3. **`frontend2/components/moving-satellite.tsx`** (NEW)
   - React Three.js component that animates a satellite along its trajectory
   - Shows the satellite as a red sphere moving in real-time
   - Displays an orbital trail showing the full path

4. **`frontend2/components/globe-view.tsx`** (MODIFIED)
   - Fetches trajectory from the backend
   - Renders the `MovingSatellite` component
   - Now shows: Earth + Mock satellites + YOUR moving satellite (red)

---

## How to Run

### 1. Start the Backend

```bash
cd /Users/the_alphalaser/Desktop/Coding/detour

# Make sure dependencies are installed
pip install fastapi uvicorn numpy python-dotenv

# Start the API server
uvicorn api.app:app --reload --port 8000
```

The backend will be available at: http://localhost:8000

### 2. Start the Frontend

```bash
cd /Users/the_alphalaser/Desktop/Coding/detour/frontend2

# Install dependencies (if not already done)
npm install

# Start the Next.js dev server
npm run dev
```

The frontend will be available at: http://localhost:3000

### 3. View the Result

Open your browser to http://localhost:3000

You should see:
- Earth in the center (rotating slowly)
- Thousands of small blue dots (mock satellites)
- **ONE RED SATELLITE** moving along its orbital path - this is YOUR `Satellite` object!

---

## What You're Seeing

The red satellite is:
1. Created using your `Satellite` class with ISS-like initial conditions
2. Propagated using simple two-body dynamics (can be upgraded to your physics engine)
3. Animated in real-time along its orbital trajectory
4. Showing both the satellite position AND its full orbital trail

---

## Next Steps

### Make it More Realistic

Replace the simple propagation in `satellite_demo.py` with your existing tools:

```python
# Instead of _simple_propagate_step, use:
from tools.propagate import propagate_orbits

# Or use your more sophisticated physics:
from engine.physics.solver import propagate_with_perturbations
```

### Add More Satellites

Modify the endpoint to return multiple satellites:

```python
@router.get("/satellites")
async def get_multiple_satellites():
    satellites = [
        {"id": "ISS", "position": [...], "velocity": [...]},
        {"id": "HST", "position": [...], "velocity": [...]},
    ]
    # Return trajectories for all
```

### Show Covariance Uncertainty

Your `Satellite` class has `cov_pos` and `cov_vel`. You can visualize this as uncertainty ellipsoids in the frontend!

### Interactive Controls

Add UI controls to:
- Select different satellites
- Change propagation duration
- Toggle trail visibility
- Show velocity vectors

---

## Troubleshooting

**Backend won't start:**
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill if needed
kill -9 <PID>
```

**Frontend shows only mock satellites:**
- Check browser console for errors
- Verify backend is running at http://localhost:8000/api/health
- Check CORS settings in `api/app.py`

**Satellite doesn't move:**
- Check browser console for trajectory fetch errors
- Verify endpoint returns data: http://localhost:8000/api/satellite-demo/iss-trajectory

---

## File Structure

```
detour/
├── api/
│   ├── app.py                           # ← Modified (added router)
│   └── routes/
│       └── satellite_demo.py            # ← NEW (trajectory endpoint)
├── engine/
│   └── models/
│       └── satellite.py                 # ← Your original Satellite class
└── frontend2/
    └── components/
        ├── globe-view.tsx               # ← Modified (added MovingSatellite)
        └── moving-satellite.tsx         # ← NEW (animation component)
```

---

## Summary

**Total changes: 4 files (2 new, 2 modified)**

✅ Backend serves your Satellite trajectory
✅ Frontend animates it in 3D
✅ Minimal changes to existing code
✅ Easy to extend with more features

Enjoy your moving satellite! 🛰️
