import urllib.request
import json
from datetime import date

_cache = {"date": None, "rates": None}

# ECB publishes rates vs EUR. We fetch CHF, GBP, USD per 1 EUR.
ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.CHF+GBP+USD.EUR.SP00.A"
    "?lastNObservations=1&format=jsondata"
)


def get_fx_rates():
    """Fetch latest ECB rates. Returns (rates_dict, date_str).
    rates_dict maps currency -> CHF equivalent of 1 unit of that currency.
    CHF is always 1.0. EUR, GBP, USD are converted via EUR cross rates.
    """
    today = date.today().isoformat()
    if _cache["date"] == today and _cache["rates"] is not None:
        return _cache["rates"], _cache["date"]

    try:
        req = urllib.request.Request(ECB_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        dataset = data["dataSets"][0]["series"]
        dims = data["structure"]["dimensions"]["series"]

        # Find which dimension index holds CURRENCY
        ccy_dim_idx = next(i for i, d in enumerate(dims) if d["id"] == "CURRENCY")
        ccy_dim = dims[ccy_dim_idx]
        ccy_map = {i: v["id"] for i, v in enumerate(ccy_dim["values"])}

        raw = {}  # currency -> rate per 1 EUR
        rate_date = None
        for series_key, series_data in dataset.items():
            parts = series_key.split(":")
            ccy_idx = int(parts[ccy_dim_idx])
            ccy = ccy_map[ccy_idx]
            obs = series_data["observations"]
            last_key = max(obs.keys(), key=int)
            raw[ccy] = obs[last_key][0]
            if rate_date is None:
                obs_dates = data["structure"]["dimensions"]["observation"][0]["values"]
                rate_date = obs_dates[int(last_key)]["id"]

        # Convert everything to "CHF per 1 unit of currency"
        eur_chf = raw.get("CHF", 1.0)  # how many CHF per 1 EUR
        rates = {"CHF": 1.0, "EUR": eur_chf}
        if "GBP" in raw:
            # raw["GBP"] = GBP per 1 EUR, so CHF per 1 GBP = eur_chf / raw["GBP"]
            rates["GBP"] = eur_chf / raw["GBP"]
        if "USD" in raw:
            rates["USD"] = eur_chf / raw["USD"]

        _cache["date"] = today
        _cache["rates"] = rates
        return rates, rate_date
    except Exception:
        return _cache.get("rates") or {"CHF": 1.0}, _cache.get("date")


def get_eur_chf_rate():
    """Backwards-compatible: returns (eur_chf_rate, date_str)."""
    rates, rate_date = get_fx_rates()
    return rates.get("EUR"), rate_date
