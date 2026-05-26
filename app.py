import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="FloodWatch Metro Manila Auto", layout="wide")

DEFAULT_CENTER = [14.5995, 120.9842]

# You may edit this list inside the app sidebar.
DEFAULT_QUERIES = [
    "Metro Manila baha today",
    "Metro Manila flood today",
    "MMDA flood alert today",
    "Manila baha now",
    "Quezon City baha now",
    "España baha now",
    "Taft baha now",
    "Marikina river overflow today",
    "Malabon baha today",
    "Valenzuela baha today",
    "Navotas baha today",
    "Pasig flood today",
]

# Optional: Add FB public Page IDs/usernames here.
# Requires a valid Meta token with approved Page Public Content Access or appropriate permissions.
DEFAULT_FB_PAGES = [
    # "MMDA",
    # "pagasa.dost.gov.ph",
    # "ManilaPIO",
]

# Rainfall monitoring points for GIS rain-risk layer.
# These are city/area centroids, not official rain gauges.
RAIN_STATIONS_METRO_MANILA = {
    "Manila": (14.5995, 120.9842),
    "Quezon City": (14.6760, 121.0437),
    "Marikina": (14.6507, 121.1029),
    "Pasig": (14.5764, 121.0851),
    "Makati": (14.5547, 121.0244),
    "Mandaluyong": (14.5794, 121.0359),
    "San Juan": (14.6042, 121.0298),
    "Caloocan": (14.7566, 121.0450),
    "Malabon": (14.6681, 120.9563),
    "Navotas": (14.6667, 120.9417),
    "Valenzuela": (14.7011, 120.9830),
    "Pasay": (14.5378, 121.0014),
    "Parañaque": (14.4793, 121.0198),
    "Las Piñas": (14.4445, 120.9939),
    "Muntinlupa": (14.4081, 121.0415),
    "Taguig": (14.5176, 121.0509),
    "Pateros": (14.5448, 121.0672),
}

RAIN_STATIONS_NATIONWIDE = {
    **RAIN_STATIONS_METRO_MANILA,
    "Baguio": (16.4023, 120.5960),
    "Tuguegarao": (17.6132, 121.7270),
    "Dagupan": (16.0430, 120.3333),
    "Olongapo": (14.8386, 120.2842),
    "San Fernando Pampanga": (15.0333, 120.6833),
    "Calamba Laguna": (14.2117, 121.1653),
    "Batangas City": (13.7565, 121.0583),
    "Naga": (13.6218, 123.1948),
    "Legazpi": (13.1391, 123.7438),
    "Iloilo City": (10.7202, 122.5621),
    "Bacolod": (10.6765, 122.9509),
    "Cebu City": (10.3157, 123.8854),
    "Tacloban": (11.2543, 125.0046),
    "Cagayan de Oro": (8.4542, 124.6319),
    "Davao City": (7.1907, 125.4553),
    "General Santos": (6.1164, 125.1716),
    "Zamboanga City": (6.9214, 122.0790),
}

FLOOD_PRONE_HINTS = {
    "Manila": "Low-lying roads, old drainage, estero/backwater effects",
    "Quezon City": "Localized ponding along major roads and low-lying barangays",
    "Marikina": "River overflow/backwater-sensitive areas",
    "Pasig": "Pasig River/creek backwater-sensitive areas",
    "Malabon": "Very low elevation, tidal/backwater-sensitive areas",
    "Navotas": "Coastal/tidal and low-lying flood-prone areas",
    "Valenzuela": "Low-lying and river/creek-adjacent communities",
    "Las Piñas": "Creek/drainage backflow and localized road flooding",
    "Parañaque": "Creek/drainage and coastal low-lying areas",
    "Muntinlupa": "Laguna Lake/backwater-sensitive areas",
}

LOCATION_GAZETTEER = {
    "españa": (14.6091, 120.9897),
    "ust": (14.6099, 120.9896),
    "taft": (14.5749, 120.9850),
    "pedro gil": (14.5768, 120.9865),
    "recto": (14.6042, 120.9839),
    "quiapo": (14.5989, 120.9841),
    "divisoria": (14.6042, 120.9701),
    "malabon": (14.6681, 120.9563),
    "navotas": (14.6667, 120.9417),
    "valenzuela": (14.7011, 120.9830),
    "marikina": (14.6507, 121.1029),
    "marikina river": (14.6409, 121.0926),
    "pasig": (14.5764, 121.0851),
    "makati": (14.5547, 121.0244),
    "quezon city": (14.6760, 121.0437),
    "araneta": (14.6182, 121.0076),
    "commonwealth": (14.6925, 121.0861),
    "edsa": (14.5832, 121.0409),
    "mandaluyong": (14.5794, 121.0359),
    "san juan": (14.6042, 121.0298),
    "pasay": (14.5378, 121.0014),
    "parañaque": (14.4793, 121.0198),
    "las piñas": (14.4445, 120.9939),
    "muntinlupa": (14.4081, 121.0415),
    "taguig": (14.5176, 121.0509),
    "c5": (14.5560, 121.0700),
}

FLOOD_KEYWORDS = [
    "baha", "flood", "flooded", "lubog", "binaha", "umaapaw", "overflow",
    "stranded", "hindi madaanan", "di madaanan", "impassable", "traffic baha",
    "knee deep", "tuhod", "ankle", "bukong", "waist", "bewang", "baywang",
    "gutter", "curb", "taas tubig", "mataas tubig", "flash flood", "not passable"
]

DEPTH_RULES = [
    (r"(ankle|bukong)", "Ankle-deep", 0.10, 0.05, 0.15),
    (r"(gutter|curb|bangketa|sidewalk)", "Gutter/curb level", 0.20, 0.10, 0.30),
    (r"(knee|tuhod)", "Knee-deep", 0.40, 0.30, 0.55),
    (r"(waist|bewang|baywang)", "Waist-deep", 0.85, 0.65, 1.10),
    (r"(chest|dibdib)", "Chest-deep", 1.20, 1.00, 1.50),
    (r"(impassable|hindi madaanan|di madaanan|not passable|stranded|lubog sasakyan)", "Impassable/vehicle risk", 0.70, 0.45, 1.20),
    (r"(lubog|binaha|baha|flooded|flood)", "Flood reported", 0.25, 0.10, 0.60),
]

TRUSTED_SOURCES = [
    "mmda", "pagasa", "pio", "official", "city", "barangay", "news"
]


def classify_text(text):
    text = "" if pd.isna(text) else str(text)
    t = text.lower()
    matched = [kw for kw in FLOOD_KEYWORDS if kw in t]
    is_flood = len(matched) > 0

    label = "No flood detected"
    depth_mid = 0.0
    depth_min = 0.0
    depth_max = 0.0

    for pattern, lbl, mid, mn, mx in DEPTH_RULES:
        if re.search(pattern, t):
            label = lbl
            depth_mid = mid
            depth_min = mn
            depth_max = mx
            break

    return is_flood, ", ".join(matched), label, depth_mid, depth_min, depth_max


def infer_location(text):
    t = str(text).lower()
    for place, coords in LOCATION_GAZETTEER.items():
        if place in t:
            return place.title(), coords[0], coords[1]
    return "Metro Manila approximate", DEFAULT_CENTER[0], DEFAULT_CENTER[1]


def confidence_score(row):
    score = 0.20
    text = str(row.get("post_text", "")).lower()
    source = str(row.get("source", "")).lower()

    matched_count = len([kw for kw in FLOOD_KEYWORDS if kw in text])
    score += min(matched_count * 0.08, 0.24)

    if any(src in source for src in TRUSTED_SOURCES):
        score += 0.20

    if row.get("has_image", False):
        score += 0.15

    if row.get("location_text", "") != "Metro Manila approximate":
        score += 0.20

    return round(min(score, 1.0), 2)


def severity(depth):
    if depth <= 0:
        return "None"
    if depth < 0.15:
        return "Low"
    if depth < 0.40:
        return "Moderate"
    if depth < 0.70:
        return "High"
    return "Critical"


def marker_color(sev):
    return {
        "Low": "green",
        "Moderate": "orange",
        "High": "red",
        "Critical": "darkred",
    }.get(sev, "gray")


def classify_rain_mmhr(mmhr):
    """Classify hourly rainfall intensity using practical mm/hr thresholds."""
    if mmhr is None or pd.isna(mmhr):
        return "Unknown", "gray", 0
    if mmhr < 2.5:
        return "Low", "green", 1
    if mmhr < 7.5:
        return "Moderate", "orange", 2
    if mmhr < 15:
        return "High", "red", 3
    return "Critical", "darkred", 4


def classify_accumulated_rain(total_mm):
    """Screening classification for accumulated rainfall over the selected time window."""
    if total_mm is None or pd.isna(total_mm):
        return "Unknown", 0
    if total_mm < 20:
        return "Low", 1
    if total_mm < 50:
        return "Moderate", 2
    if total_mm < 100:
        return "High", 3
    return "Critical", 4


def possible_flood_risk_dynamic(area_name, past_total_mm, forecast_total_mm, max_hourly_mm):
    """
    Screening risk using accumulated past rain, projected rain, peak hourly rain,
    and a simple flood-prone bonus for low-lying/backwater-sensitive locations.
    """
    _, peak_score = classify_rain_mmhr(max_hourly_mm)[0], classify_rain_mmhr(max_hourly_mm)[2]
    _, past_score = classify_accumulated_rain(past_total_mm)
    _, forecast_score = classify_accumulated_rain(forecast_total_mm)
    flood_prone_bonus = 1 if area_name in FLOOD_PRONE_HINTS else 0

    total = max(peak_score, past_score, forecast_score) + flood_prone_bonus
    if total <= 1:
        return "Low"
    if total == 2:
        return "Moderate"
    if total == 3:
        return "High"
    return "Critical"


def risk_color(risk):
    return {
        "Low": "green",
        "Moderate": "orange",
        "High": "red",
        "Critical": "darkred",
    }.get(risk, "gray")


def rainfall_trend(past_total_mm, forecast_total_mm, past_hours, forecast_hours):
    """Compare average past rainfall rate vs forecast rainfall rate."""
    try:
        past_rate = float(past_total_mm or 0) / max(float(past_hours), 1.0)
        forecast_rate = float(forecast_total_mm or 0) / max(float(forecast_hours), 1.0)
    except Exception:
        return "Unknown"

    if forecast_rate > past_rate * 1.25 and (forecast_rate - past_rate) >= 0.10:
        return "Increasing"
    if forecast_rate < past_rate * 0.75 and (past_rate - forecast_rate) >= 0.10:
        return "Decreasing"
    return "Stable"


def haversine_km(lat1, lon1, lat2, lon2):
    """Approximate distance in kilometers between two lat/lon points."""
    import math
    r = 6371.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearby_flood_report_summary(flood_df, lat, lon, radius_km=6):
    """Count and summarize confirmed flood reports near a rainfall node."""
    if flood_df is None or flood_df.empty:
        return 0, "No nearby confirmed flood reports from current feed."

    nearby = []
    for _, row in flood_df.dropna(subset=["lat", "lon"]).iterrows():
        try:
            d = haversine_km(lat, lon, row["lat"], row["lon"])
            if d <= radius_km:
                nearby.append((d, row))
        except Exception:
            continue

    if not nearby:
        return 0, f"No confirmed flood reports within {radius_km} km."

    nearby = sorted(nearby, key=lambda x: x[0])
    snippets = []
    for d, row in nearby[:3]:
        snippets.append(
            f"{row.get('location_text', 'Unknown location')} "
            f"({row.get('severity', 'Unknown')}, {d:.1f} km)"
        )
    return len(nearby), "; ".join(snippets)


def rainfall_node_tooltip(row, nearby_count, trend):
    """HTML hover tooltip for each city rainfall intelligence node."""
    return f"""
    <div style="font-size: 12px; min-width: 240px;">
      <b>{row['area']}</b><br>
      Past 48h / selected past: <b>{row.get('past_total_mm', 'No data')} mm</b><br>
      Next 96h / selected forecast: <b>{row.get('forecast_total_mm', 'No data')} mm</b><br>
      Peak hourly rain: <b>{row.get('max_hourly_mm', 'No data')} mm/hr</b><br>
      Flood-risk estimate: <b>{row.get('possible_flood_risk', 'Unknown')}</b><br>
      Nearby flood reports: <b>{nearby_count}</b><br>
      Trend: <b>{trend}</b>
    </div>
    """


def forecast_rainfall_chart_html(future_df, width=420, height=150):
    """Create a lightweight SVG bar chart for the forecast rainfall popup."""
    try:
        if future_df is None or future_df.empty:
            return "<div><b>Forecast rainfall chart:</b><br>No forecast rainfall data.</div>"

        chart_df = future_df.copy().reset_index(drop=True)
        chart_df = chart_df[["time", "rain_mm"]].dropna()
        if chart_df.empty:
            return "<div><b>Forecast rainfall chart:</b><br>No forecast rainfall data.</div>"

        max_rain = max(float(chart_df["rain_mm"].max()), 0.1)
        left_pad, right_pad, top_pad, bottom_pad = 44, 10, 16, 34
        plot_w = width - left_pad - right_pad
        plot_h = height - top_pad - bottom_pad
        n = len(chart_df)
        bar_w = max(1.0, plot_w / max(n, 1) * 0.75)

        bars = []
        for i, row in chart_df.iterrows():
            rain = float(row["rain_mm"] or 0)
            x = left_pad + (i + 0.15) * plot_w / max(n, 1)
            h = (rain / max_rain) * plot_h if max_rain > 0 else 0
            y = top_pad + plot_h - h
            fill = "#0b66c3" if rain > 0 else "#d9e6f2"
            time_label = pd.Timestamp(row["time"]).strftime("%b %d %H:%M")
            bars.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{fill}">'
                f'<title>{time_label}: {rain:.1f} mm</title></rect>'
            )

        peak_idx = int(chart_df["rain_mm"].idxmax())
        peak_row = chart_df.loc[peak_idx]
        peak_mm = float(peak_row["rain_mm"] or 0)
        peak_time = pd.Timestamp(peak_row["time"]).strftime("%b %d, %I:%M %p")

        grid = []
        for frac in [0, 0.5, 1.0]:
            y = top_pad + plot_h - frac * plot_h
            val = frac * max_rain
            grid.append(f'<line x1="{left_pad}" y1="{y:.1f}" x2="{width-right_pad}" y2="{y:.1f}" stroke="#e3e8ef" stroke-width="1"/>')
            grid.append(f'<text x="4" y="{y+4:.1f}" font-size="10" fill="#475569">{val:.1f}</text>')

        start_label = pd.Timestamp(chart_df["time"].iloc[0]).strftime("%b %d %H:%M")
        end_label = pd.Timestamp(chart_df["time"].iloc[-1]).strftime("%b %d %H:%M")

        return (
            '<div style="margin-top:8px; font-family:Arial, sans-serif;">'
            '<b>Forecast rainfall timing</b><br>'
            f'Peak forecast rain: <b>{peak_mm:.1f} mm/hr</b><br>'
            f'Peak forecast time: <b>{peak_time}</b><br>'
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            'style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; margin-top:6px;">'
            f'<text x="{left_pad}" y="12" font-size="11" fill="#334155">Forecast rainfall (mm/hr)</text>'
            + ''.join(grid) + ''.join(bars) +
            f'<text x="{left_pad}" y="{height-10}" font-size="10" fill="#64748b">{start_label}</text>'
            f'<text x="{width-115}" y="{height-10}" font-size="10" fill="#64748b">{end_label}</text>'
            '</svg></div>'
        )
    except Exception as e:
        return f"<div><b>Forecast rainfall chart:</b><br>Chart failed: {e}</div>"


@st.cache_data(ttl=600)
def fetch_open_meteo_rainfall(stations, past_hours=48, forecast_hours=96):
    """
    Fetch hourly rainfall for the last N hours and next N hours from Open-Meteo.
    Uses forecast API with past_days and forecast_days. No API key required.
    Results are screening-level and should be checked against PAGASA/radar/local reports.
    """
    rows = []
    now_local = pd.Timestamp.now(tz="Asia/Manila").floor("h")
    past_start = now_local - pd.Timedelta(hours=int(past_hours))
    forecast_end = now_local + pd.Timedelta(hours=int(forecast_hours))

    # Add buffer days so the hourly API covers the selected windows.
    past_days = max(2, int((past_hours + 23) // 24))
    forecast_days = max(4, int((forecast_hours + 23) // 24) + 1)

    for area, (lat, lon) in stations.items():
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation,rain,showers",
                "timezone": "Asia/Manila",
                "past_days": past_days,
                "forecast_days": forecast_days,
            }
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            precip = hourly.get("precipitation", [])
            rain = hourly.get("rain", [])
            showers = hourly.get("showers", [])

            hdf = pd.DataFrame({
                "time": pd.to_datetime(times, errors="coerce"),
                "precipitation": pd.to_numeric(pd.Series(precip), errors="coerce"),
                "rain": pd.to_numeric(pd.Series(rain), errors="coerce"),
                "showers": pd.to_numeric(pd.Series(showers), errors="coerce"),
            })
            if hdf.empty:
                raise ValueError("No hourly rainfall data returned")

            hdf["time"] = hdf["time"].dt.tz_localize("Asia/Manila", nonexistent="shift_forward", ambiguous="NaT")
            hdf["rain_mm"] = hdf[["precipitation", "rain", "showers"]].max(axis=1).fillna(0)

            past_df = hdf[(hdf["time"] >= past_start) & (hdf["time"] <= now_local)]
            future_df = hdf[(hdf["time"] > now_local) & (hdf["time"] <= forecast_end)]
            window_df = hdf[(hdf["time"] >= past_start) & (hdf["time"] <= forecast_end)]

            current_row = hdf[hdf["time"] <= now_local].tail(1)
            current_mmhr = float(current_row["rain_mm"].iloc[0]) if not current_row.empty else 0.0
            past_total = float(past_df["rain_mm"].sum()) if not past_df.empty else 0.0
            forecast_total = float(future_df["rain_mm"].sum()) if not future_df.empty else 0.0
            total_window = past_total + forecast_total
            max_hourly = float(window_df["rain_mm"].max()) if not window_df.empty else 0.0
            peak_time = window_df.loc[window_df["rain_mm"].idxmax(), "time"].isoformat() if not window_df.empty else ""
            forecast_peak_mm = float(future_df["rain_mm"].max()) if not future_df.empty else 0.0
            forecast_peak_time = future_df.loc[future_df["rain_mm"].idxmax(), "time"].isoformat() if not future_df.empty else ""
            forecast_chart_html = forecast_rainfall_chart_html(future_df)

            rain_level, color, _ = classify_rain_mmhr(current_mmhr)
            past_level, _ = classify_accumulated_rain(past_total)
            forecast_level, _ = classify_accumulated_rain(forecast_total)
            risk = possible_flood_risk_dynamic(area, past_total, forecast_total, max_hourly)
            trend = rainfall_trend(past_total, forecast_total, past_hours, forecast_hours)

            rows.append({
                "area": area,
                "lat": lat,
                "lon": lon,
                "current_mmhr": round(current_mmhr, 2),
                "past_total_mm": round(past_total, 1),
                "forecast_total_mm": round(forecast_total, 1),
                "total_window_mm": round(total_window, 1),
                "max_hourly_mm": round(max_hourly, 2),
                "peak_time": peak_time,
                "forecast_peak_mm": round(forecast_peak_mm, 2),
                "forecast_peak_time": forecast_peak_time,
                "forecast_chart_html": forecast_chart_html,
                "rain_level": rain_level,
                "past_accum_level": past_level,
                "forecast_accum_level": forecast_level,
                "possible_flood_risk": risk,
                "trend": trend,
                "color": risk_color(risk),
                "timestamp": now_local.isoformat(),
                "flood_prone_hint": FLOOD_PRONE_HINTS.get(area, "General rainfall screening point"),
                "source": f"Open-Meteo hourly precipitation: past {past_hours}h + forecast {forecast_hours}h"
            })
        except Exception as e:
            rows.append({
                "area": area,
                "lat": lat,
                "lon": lon,
                "current_mmhr": None,
                "past_total_mm": None,
                "forecast_total_mm": None,
                "total_window_mm": None,
                "max_hourly_mm": None,
                "peak_time": "",
                "forecast_peak_mm": None,
                "forecast_peak_time": "",
                "forecast_chart_html": "<div>No forecast rainfall chart available.</div>",
                "rain_level": "Unknown",
                "past_accum_level": "Unknown",
                "forecast_accum_level": "Unknown",
                "possible_flood_risk": "Unknown",
                "trend": "Unknown",
                "color": "gray",
                "timestamp": datetime.now().isoformat(),
                "flood_prone_hint": f"Rain fetch failed: {e}",
                "source": "Open-Meteo hourly precipitation"
            })
    return pd.DataFrame(rows)


def rain_circle_radius(total_mm):
    if total_mm is None or pd.isna(total_mm):
        return 8
    return 8 + min(float(total_mm) / 3.0, 35)


def parse_feed_datetime(value):
    """Parse RSS/Facebook timestamps into timezone-aware UTC datetime."""
    if not value:
        return None

    # Google News/feedparser entries may provide a parsed struct_time.
    if hasattr(value, "tm_year"):
        return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Fallback for RSS strings like: Sun, 17 May 2026 08:15:00 GMT
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_recent(timestamp_value, max_age_hours):
    dt = parse_feed_datetime(timestamp_value)
    if dt is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return dt >= cutoff


def normalize_timestamp(timestamp_value):
    dt = parse_feed_datetime(timestamp_value)
    if dt is None:
        return str(timestamp_value)
    return dt.isoformat()


@st.cache_data(ttl=60)
def fetch_google_news(query, limit=10, max_age_hours=24):
    rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-PH&gl=PH&ceid=PH:en"
    feed = feedparser.parse(rss_url)
    rows = []
    added = 0
    for entry in feed.entries:
        published_value = entry.get("published_parsed") or entry.get("published", "")
        if not is_recent(published_value, max_age_hours):
            continue

        text = f"{entry.get('title', '')}. {entry.get('summary', '')}"
        location, lat, lon = infer_location(text)
        rows.append({
            "source": entry.get("source", {}).get("title", "Google News"),
            "post_text": text,
            "location_text": location,
            "lat": lat,
            "lon": lon,
            "timestamp": normalize_timestamp(published_value),
            "has_image": False,
            "url": entry.get("link", ""),
            "data_source": "Google News RSS"
        })
        added += 1
        if added >= limit:
            break
    return rows


@st.cache_data(ttl=60)
def fetch_fb_public_page_posts(page_ids, token, limit=10, max_age_hours=24):
    rows = []
    if not token or not page_ids:
        return rows

    for page in page_ids:
        page = page.strip()
        if not page:
            continue

        url = f"https://graph.facebook.com/v20.0/{page}/posts"
        since_time = int((datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).timestamp())
        params = {
            "access_token": token,
            "fields": "message,created_time,permalink_url,attachments{media,type,url}",
            "since": since_time,
            "limit": limit
        }

        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                rows.append({
                    "source": f"FB:{page}",
                    "post_text": f"Facebook API error for {page}: {r.text[:300]}",
                    "location_text": "API error",
                    "lat": DEFAULT_CENTER[0],
                    "lon": DEFAULT_CENTER[1],
                    "timestamp": datetime.now().isoformat(),
                    "has_image": False,
                    "url": "",
                    "data_source": "Facebook Graph API"
                })
                continue

            data = r.json().get("data", [])
            for item in data:
                msg = item.get("message", "")
                if not msg:
                    continue

                created_time = item.get("created_time", "")
                if not is_recent(created_time, max_age_hours):
                    continue

                location, lat, lon = infer_location(msg)
                rows.append({
                    "source": f"FB:{page}",
                    "post_text": msg,
                    "location_text": location,
                    "lat": lat,
                    "lon": lon,
                    "timestamp": normalize_timestamp(created_time),
                    "has_image": "attachments" in item,
                    "url": item.get("permalink_url", ""),
                    "data_source": "Facebook Graph API"
                })

        except Exception as e:
            rows.append({
                "source": f"FB:{page}",
                "post_text": f"Facebook API fetch failed for {page}: {e}",
                "location_text": "API error",
                "lat": DEFAULT_CENTER[0],
                "lon": DEFAULT_CENTER[1],
                "timestamp": datetime.now().isoformat(),
                "has_image": False,
                "url": "",
                "data_source": "Facebook Graph API"
            })

    return rows


def process_rows(rows):
    if not rows:
        return pd.DataFrame(columns=[
            "source", "post_text", "location_text", "lat", "lon", "timestamp",
            "has_image", "url", "data_source", "is_flood", "matched_keywords",
            "depth_label", "depth_m", "depth_min_m", "depth_max_m",
            "confidence", "severity", "timestamp_dt"
        ])

    df = pd.DataFrame(rows)

    # Remove duplicated links/text and keep newest items first.
    if "url" in df.columns:
        df = df.drop_duplicates(subset=["url"], keep="first")
    df = df.drop_duplicates(subset=["post_text"], keep="first")
    df["timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.sort_values("timestamp_dt", ascending=False, na_position="last").reset_index(drop=True)

    results = df["post_text"].apply(classify_text)
    df[["is_flood", "matched_keywords", "depth_label", "depth_m", "depth_min_m", "depth_max_m"]] = pd.DataFrame(results.tolist(), index=df.index)
    df["confidence"] = df.apply(confidence_score, axis=1)
    df["severity"] = df["depth_m"].apply(severity)
    return df


st.title("FloodWatch Metro Manila Auto MVP")
st.caption("Latest-only mode: automatically checks recent public web/news feeds and optional approved Facebook public Page API.")

with st.sidebar:
    st.header("Automatic Sources")

    use_news = st.checkbox("Use Google News RSS search", value=True)
    query_text = st.text_area(
        "Search queries",
        value="\n".join(DEFAULT_QUERIES),
        height=180
    )
    per_query_limit = st.slider("Items per query", 3, 30, 10)
    max_age_hours = st.slider("Only show reports from last N hours", 1, 72, 24)

    st.divider()
    st.subheader("Dynamic GIS Rainfall Risk Layer")
    show_rain_layer = st.checkbox("Show rainfall layer from Open-Meteo", value=True)
    rainfall_coverage = st.selectbox(
        "Rainfall coverage",
        ["Metro Manila", "Nationwide key cities"],
        index=0
    )
    past_rain_hours = st.slider("Past rainfall accumulation window (hours)", 1, 48, 48)
    forecast_rain_hours = st.slider("Projected rainfall window (hours)", 1, 96, 96)
    st.caption("Rainfall layer uses past accumulation + forecast rainfall. This is possible flood risk, not confirmed flooding.")

    st.divider()
    st.subheader("Optional Facebook Public Page API")
    st.caption("Requires Meta-approved access/token. Leave blank if unavailable.")
    use_fb = st.checkbox("Use Facebook Graph API", value=False)
    fb_token = st.text_input("FB_ACCESS_TOKEN", value=os.getenv("FB_ACCESS_TOKEN", ""), type="password")
    fb_pages_text = st.text_area("Public Page IDs/usernames", value="\n".join(DEFAULT_FB_PAGES), height=120)

    refresh = st.button("Refresh now")

rows = []

if use_news:
    queries = [q.strip() for q in query_text.splitlines() if q.strip()]
    for q in queries:
        rows.extend(fetch_google_news(q, per_query_limit, max_age_hours))

if use_fb:
    fb_pages = [p.strip() for p in fb_pages_text.splitlines() if p.strip()]
    rows.extend(fetch_fb_public_page_posts(fb_pages, fb_token, per_query_limit, max_age_hours))

rainfall_df = pd.DataFrame()
if show_rain_layer:
    selected_stations = RAIN_STATIONS_METRO_MANILA if rainfall_coverage == "Metro Manila" else RAIN_STATIONS_NATIONWIDE
    rainfall_df = fetch_open_meteo_rainfall(selected_stations, past_rain_hours, forecast_rain_hours)

df = process_rows(rows)
flood_df = df[df["is_flood"] == True].copy()

st.success(f"Showing latest reports only: last {max_age_hours} hour(s). Cache refresh: every 60 seconds.")

if show_rain_layer and not rainfall_df.empty:
    high_rain_count = int(rainfall_df["rain_level"].isin(["High", "Critical"]).sum())
    high_flood_risk_count = int(rainfall_df["possible_flood_risk"].isin(["High", "Critical"]).sum())
    max_total_rain = round(float(rainfall_df["total_window_mm"].max()), 1) if "total_window_mm" in rainfall_df else 0
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Rainfall points", len(rainfall_df))
    r2.metric("High/Critical current rain", high_rain_count)
    r3.metric("Possible flood-risk points", high_flood_risk_count)
    r4.metric("Max rain window", f"{max_total_rain} mm")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Collected items", len(df))
c2.metric("Flood-related items", len(flood_df))
c3.metric("Critical reports", int((flood_df["severity"] == "Critical").sum()))
c4.metric("Avg confidence", round(flood_df["confidence"].mean(), 2) if len(flood_df) else 0)

left, right = st.columns([2, 1])

with left:
    st.subheader("Flood + Dynamic Rainfall Risk Map")
    m = folium.Map(location=DEFAULT_CENTER, zoom_start=11, tiles="OpenStreetMap")

    if show_rain_layer and not rainfall_df.empty:
        rain_group = folium.FeatureGroup(name="Rainfall / Possible Flood Risk", show=True)
        for _, rrow in rainfall_df.dropna(subset=["lat", "lon"]).iterrows():
            total_mm = rrow.get("total_window_mm")
            nearby_count, nearby_summary = nearby_flood_report_summary(
                flood_df, rrow["lat"], rrow["lon"], radius_km=6
            )
            trend = rrow.get("trend", rainfall_trend(
                rrow.get("past_total_mm"), rrow.get("forecast_total_mm"),
                past_rain_hours, forecast_rain_hours
            ))

            popup = f"""
            <b>{rrow['area']} Rainfall Intelligence Node</b><br>
            Current rainfall: {rrow.get('current_mmhr', 'No data')} mm/hr<br>
            Last {past_rain_hours}h accumulated rainfall: {rrow.get('past_total_mm', 'No data')} mm<br>
            Next {forecast_rain_hours}h projected rainfall: {rrow.get('forecast_total_mm', 'No data')} mm<br>
            Total rain window: {rrow.get('total_window_mm', 'No data')} mm<br>
            Peak hourly rain: {rrow.get('max_hourly_mm', 'No data')} mm/hr<br>
            Peak time within full window: {rrow.get('peak_time', '')}<br>
            Peak forecast rain: <b>{rrow.get('forecast_peak_mm', 'No data')} mm/hr</b><br>
            Peak forecast time: <b>{rrow.get('forecast_peak_time', '')}</b><br>
            {rrow.get('forecast_chart_html', '')}
            <br>
            Flood-risk estimate: <b>{rrow['possible_flood_risk']}</b><br>
            Nearby flood reports within 6 km: <b>{nearby_count}</b><br>
            Nearby report summary: {nearby_summary}<br>
            Trend: <b>{trend}</b><br>
            Local hint: {rrow['flood_prone_hint']}<br>
            Time checked: {rrow['timestamp']}<br>
            Source: {rrow['source']}
            """
            folium.CircleMarker(
                location=[rrow["lat"], rrow["lon"]],
                radius=rain_circle_radius(total_mm),
                popup=folium.Popup(popup, max_width=460),
                tooltip=folium.Tooltip(
                    rainfall_node_tooltip(rrow, nearby_count, trend),
                    sticky=True
                ),
                color=rrow["color"],
                fill=True,
                fill_opacity=0.25,
                weight=2
            ).add_to(rain_group)
        rain_group.add_to(m)

    flood_group = folium.FeatureGroup(name="Confirmed Flood Reports", show=True)
    for _, row in flood_df.dropna(subset=["lat", "lon"]).iterrows():
        popup = f"""
        <b>{row['severity']} - {row['depth_label']}</b><br>
        Estimated depth: {row['depth_min_m']:.2f}–{row['depth_max_m']:.2f} m<br>
        Confidence: {row['confidence']}<br>
        Source: {row['source']}<br>
        Data source: {row['data_source']}<br>
        Location: {row['location_text']}<br>
        Text: {str(row['post_text'])[:300]}<br>
        <a href="{row.get('url', '')}" target="_blank">Open source</a>
        """
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=8 + row["confidence"] * 8,
            popup=folium.Popup(popup, max_width=400),
            color=marker_color(row["severity"]),
            fill=True,
            fill_opacity=0.70
        ).add_to(flood_group)

    flood_group.add_to(m)
    folium.LayerControl().add_to(m)

    st_folium(m, width=None, height=600)

with right:
    st.subheader("Severity Summary")
    if len(flood_df):
        st.dataframe(
            flood_df.groupby(["severity", "data_source"])
            .size()
            .reset_index(name="reports")
            .sort_values("reports", ascending=False),
            use_container_width=True
        )
    else:
        st.info("No flood-related items detected from current sources.")

if show_rain_layer and not rainfall_df.empty:
    st.subheader("Rainfall / Possible Flood Risk Layer")
    st.dataframe(
        rainfall_df[["area", "current_mmhr", "past_total_mm", "forecast_total_mm", "total_window_mm", "max_hourly_mm", "peak_time", "forecast_peak_mm", "forecast_peak_time", "possible_flood_risk", "trend", "timestamp", "flood_prone_hint", "source"]]
        .sort_values(["possible_flood_risk", "total_window_mm"], ascending=[True, False]),
        use_container_width=True
    )

st.subheader("Detected Flood Reports")
if len(flood_df):
    cols = ["timestamp", "data_source", "source", "location_text", "severity", "depth_label",
            "depth_min_m", "depth_max_m", "confidence", "matched_keywords", "post_text", "url"]
    st.dataframe(
        flood_df[cols].sort_values(["confidence"], ascending=False),
        use_container_width=True
    )
else:
    st.warning("No flood reports found. Try adding more queries or enabling an approved Facebook source.")

st.subheader("All Collected Items")
st.dataframe(df, use_container_width=True)

st.download_button(
    "Download detected flood reports",
    flood_df.to_csv(index=False).encode("utf-8"),
    "detected_flood_reports.csv",
    "text/csv"
)

st.info("""
This version removes manual CSV import. It fetches recent public web/news sources, optional approved Facebook public Page API access, and a dynamic Open-Meteo rainfall layer using past 48h accumulation and up to 96h projected rainfall.
Rainfall points are screening indicators for possible flooding, not confirmed flood depths. Confirm with local reports, PAGASA/radar, river levels, tide/backwater information, or field validation.
For Facebook, avoid login scraping, private posts, or bypassing platform controls.
""")
