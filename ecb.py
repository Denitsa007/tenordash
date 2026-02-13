import urllib.request
import json
from datetime import date

_cache = {"date": None, "rate": None}

ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.CHF.EUR.SP00.A"
    "?lastNObservations=1&format=jsondata"
)


def get_eur_chf_rate():
    """Fetch latest EUR/CHF rate from ECB. Returns (rate, date_str) or (None, None)."""
    today = date.today().isoformat()
    if _cache["date"] == today and _cache["rate"] is not None:
        return _cache["rate"], _cache["date"]

    try:
        req = urllib.request.Request(ECB_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        series = data["dataSets"][0]["series"]["0:0:0:0:0"]
        obs = series["observations"]
        last_key = max(obs.keys(), key=int)
        rate = obs[last_key][0]

        dates = data["structure"]["dimensions"]["observation"][0]["values"]
        rate_date = dates[int(last_key)]["id"]

        _cache["date"] = today
        _cache["rate"] = rate
        return rate, rate_date
    except Exception:
        return _cache.get("rate"), _cache.get("date")
