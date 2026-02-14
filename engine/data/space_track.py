import os
import requests


def space_track_login():
    username = os.environ.get("SPACE_TRACK_USER", "")
    password = os.environ.get("SPACE_TRACK_PASS", "")
    if not username or not password:
        raise RuntimeError("SPACE_TRACK_USER and SPACE_TRACK_PASS env vars required")

    session = requests.Session()
    login_url = "https://www.space-track.org/ajaxauth/login"
    payload = {"identity": username, "password": password}

    resp = session.post(login_url, data=payload, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError("Space-Track login failed")

    return session
