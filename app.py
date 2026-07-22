import os
import json
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash
import requests
import uuid
import datetime

NOTITIES_FILE = "notities.json"
USERS_FILE = "users.json"

def laad_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
STATUS_FILE = "status.json"

def laad_status():
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)    

def laad_notities():
    try:
        with open(NOTITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_notities(data):
    with open(NOTITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_id():
    return request.cookies.get("user_id") or getattr(request, "nieuw_user_id", "") or ""
GEOCODE_CACHE_FILE = "geocode_cache.json"

def laad_geocode_cache():
    try:
        with open(GEOCODE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_geocode_cache(data):
    with open(GEOCODE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def geocode_adres(adres, stad):
    query = ", ".join([x for x in [adres, stad] if x])
    if not query:
        return None
    cache = laad_geocode_cache()
    if query in cache:
        return cache[query]
    try:
        headers = {"User-Agent": "RecycleFind/1.0"}
        params = {"q": query, "format": "json", "limit": 1}
        resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=8)
        resultaten = resp.json()
        if resultaten:
            lat = float(resultaten[0]["lat"])
            lon = float(resultaten[0]["lon"])
            cache[query] = {"lat": lat, "lon": lon}
            bewaar_geocode_cache(cache)
            return cache[query]
    except Exception as e:
        print(f"Geocode error: {e}")
    return None
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "verander-dit-later-in-iets-geheims")
@app.before_request
@app.before_request
def vereis_login():
    toegestaan = ["login", "static"]
    if request.endpoint not in toegestaan and not session.get("ingelogd"):
        return redirect(url_for("login"))
def zorg_voor_user_id():
    if not request.cookies.get("user_id"):
        request.nieuw_user_id = str(uuid.uuid4())
    else:
        request.nieuw_user_id = None

@app.after_request
def zet_user_cookie(response):
    if getattr(request, "nieuw_user_id", None):
        response.set_cookie("user_id", request.nieuw_user_id, max_age=60*60*24*365*5)
    return response

with open("bedrijven.json", "r", encoding="utf-8") as f:
    ENF_BEDRIJVEN = json.load(f)

LANDEN = sorted(set(b["land"] for b in ENF_BEDRIJVEN))

REGIO_PER_LAND = {}
for b in ENF_BEDRIJVEN:
    land = b["land"]
    regio = b["regio"]
    if land not in REGIO_PER_LAND:
        REGIO_PER_LAND[land] = set()
    REGIO_PER_LAND[land].add(regio)
REGIO_PER_LAND = {l: sorted(r) for l, r in REGIO_PER_LAND.items()}

def haal_bedrijf_details(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        tekst = soup.get_text()
        details = {}
        website = soup.find("a", href=lambda h: h and h.startswith("http") and "enfpaper" not in h)
        if website:
            details["website"] = website["href"]
        for tag in soup.find_all(["td", "div", "span"]):
            t = tag.get_text(strip=True)
            if "+" in t and any(c.isdigit() for c in t) and len(t) < 30:
                details["telefoon"] = t
                break
        lines = [l.strip() for l in tekst.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "No. Staff" in line and i+1 < len(lines):
                details["medewerkers"] = lines[i+1]
            if "Type of Recycled" in line and i+1 < len(lines):
                details["materialen_detail"] = lines[i+1]

        adres_tag = soup.find("span", {"itemprop": "streetAddress"})
        stad_tag = soup.find("span", {"itemprop": "addressLocality"})
        if adres_tag:
            details["adres"] = adres_tag.get_text(strip=True)
        if stad_tag:
            details["stad"] = stad_tag.get_text(strip=True)

        if details.get("adres") and details.get("stad"):
            geo = geocode_adres(details["adres"], details["stad"])
            if geo:
                details["lat_precies"] = geo["lat"]
                details["lon_precies"] = geo["lon"]

        return details
    except:
        return {}

HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RecycleFind — Global Recycling Intelligence</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        /* ============================================
           DESIGN SYSTEM — RECYCLEFIND
           ============================================ */

        /* TOKENS */
        :root {
            /* Colors */
            --brand-50:  #eff6ff;
            --brand-100: #dbeafe;
            --brand-200: #bfdbfe;
            --brand-300: #93c5fd;
            --brand-400: #60a5fa;
            --brand-500: #3b82f6;
            --brand-600: #2563eb;
            --brand-700: #1d4ed8;
            --brand-800: #1e40af;
            --brand-900: #1e3a8a;

            --gray-50:  #f8fafc;
            --gray-100: #f1f5f9;
            --gray-200: #e2e8f0;
            --gray-300: #cbd5e1;
            --gray-400: #94a3b8;
            --gray-500: #64748b;
            --gray-600: #475569;
            --gray-700: #334155;
            --gray-800: #1e293b;
            --gray-900: #0f172a;

            --green-50:  #f0fdf4;
            --green-500: #22c55e;
            --green-600: #16a34a;

            --orange-50:  #fff7ed;
            --orange-500: #f97316;
            --orange-600: #ea580c;

            --red-50:  #fef2f2;
            --red-500: #ef4444;

            /* Typography */
            --font: "Inter", -apple-system, sans-serif;
            --text-xs:   0.7rem;
            --text-sm:   0.8rem;
            --text-base: 0.9rem;
            --text-lg:   1.05rem;
            --text-xl:   1.2rem;
            --text-2xl:  1.5rem;
            --text-3xl:  2rem;
            --text-4xl:  2.8rem;
            --text-5xl:  3.5rem;

            /* Spacing */
            --space-1: 4px;
            --space-2: 8px;
            --space-3: 12px;
            --space-4: 16px;
            --space-5: 20px;
            --space-6: 24px;
            --space-8: 32px;
            --space-10: 40px;
            --space-12: 48px;
            --space-16: 64px;

            /* Radius */
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 20px;
            --radius-full: 9999px;

            /* Shadows */
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.1);
            --shadow-xl: 0 16px 48px rgba(0,0,0,0.12);
            --shadow-brand: 0 4px 14px rgba(37,99,235,0.25);

            /* Transitions */
            --transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
        }

        /* RESET */
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body { font-family: var(--font); background: var(--gray-50); color: var(--gray-800); min-height: 100vh; -webkit-font-smoothing: antialiased; }

        /* ============================================
           NAVBAR
           ============================================ */
        .navbar {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(255,255,255,0.9);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--gray-200);
            height: 56px;
            display: flex;
            align-items: center;
            padding: 0 var(--space-8);
            gap: var(--space-8);
        }
        .navbar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            flex-shrink: 0;
        }
        .navbar-logo em { color: var(--brand-600); font-style: normal; }
        .navbar-divider { width: 1px; height: 20px; background: var(--gray-200); }
        .navbar-stat { font-size: var(--text-xs); color: var(--gray-400); white-space: nowrap; }
        .navbar-stat strong { color: var(--brand-600); font-weight: 600; }
        .navbar-right { margin-left: auto; display: flex; align-items: center; gap: var(--space-3); }
        .btn-nav {
            font-size: var(--text-sm);
            font-weight: 500;
            padding: 6px 14px;
            border-radius: var(--radius-sm);
            border: none;
            cursor: pointer;
            font-family: var(--font);
            transition: var(--transition);
            text-decoration: none;
        }
        .btn-nav-ghost { background: transparent; color: var(--gray-600); }
        .btn-nav-ghost:hover { background: var(--gray-100); color: var(--gray-900); }
        .btn-nav-primary { background: var(--brand-600); color: #fff; }
        .btn-nav-primary:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }

        /* ============================================
           HERO
           ============================================ */
        .hero {
            background: linear-gradient(160deg, var(--brand-900) 0%, var(--brand-800) 40%, var(--brand-700) 100%);
            padding: var(--space-16) var(--space-10) var(--space-12);
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        .hero::after {
            content: "";
            position: absolute;
            inset: 0;
            background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            pointer-events: none;
        }
        .hero-content { position: relative; z-index: 1; max-width: 720px; margin: 0 auto; }
        .hero-badge {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: var(--brand-200);
            padding: 5px 14px;
            border-radius: var(--radius-full);
            font-size: var(--text-xs);
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            margin-bottom: var(--space-5);
        }
        .hero h1 {
            font-size: var(--text-5xl);
            font-weight: 900;
            color: #fff;
            letter-spacing: -2px;
            line-height: 1.05;
            margin-bottom: var(--space-4);
        }
        .hero h1 em { color: var(--brand-300); font-style: normal; }
        .hero-sub {
            color: rgba(255,255,255,0.65);
            font-size: var(--text-lg);
            margin-bottom: var(--space-8);
            font-weight: 400;
        }

        /* ============================================
           SEARCH
           ============================================ */
        .search-container {
            background: rgba(255,255,255,0.07);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: var(--radius-xl);
            padding: var(--space-5);
            max-width: 860px;
            margin: 0 auto;
        }
        .search-row {
            display: flex;
            gap: var(--space-2);
            flex-wrap: wrap;
            justify-content: center;
        }
        .search-input, .search-select {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 9px 13px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-800);
            outline: none;
            transition: var(--transition);
        }
        .search-input { width: 200px; }
        .search-input::placeholder { color: var(--gray-400); }
        .search-select { width: 155px; cursor: pointer; }
        .search-input:focus, .search-select:focus {
            border-color: var(--brand-400);
            box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
        }
        .btn-search {
            background: var(--brand-500);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px 20px;
            font-size: var(--text-sm);
            font-weight: 700;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
        }
        .btn-search:hover { background: var(--brand-400); transform: translateY(-1px); box-shadow: var(--shadow-brand); }

        /* ============================================
           STATS BAR
           ============================================ */
        .stats-bar {
            background: #fff;
            border-bottom: 1px solid var(--gray-200);
            padding: var(--space-4) var(--space-10);
            display: flex;
            justify-content: center;
            gap: var(--space-12);
        }
        .stat { text-align: center; }
        .stat-num { font-size: var(--text-2xl); font-weight: 800; color: var(--brand-600); letter-spacing: -0.5px; }
        .stat-label { font-size: var(--text-xs); color: var(--gray-400); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 2px; }

        /* ============================================
           MAIN LAYOUT
           ============================================ */
        .main {
            max-width: 1440px;
            margin: var(--space-6) auto;
            padding: 0 var(--space-6);
            display: flex;
            gap: var(--space-5);
            align-items: flex-start;
        }

        /* ============================================
           FILTERS SIDEBAR
           ============================================ */
        .filters-panel {
            width: 220px;
            flex-shrink: 0;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            box-shadow: var(--shadow-sm);
        }
        .filters-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-4);
        }
        .filter-group { margin-bottom: var(--space-4); }
        .filter-label {
            font-size: var(--text-xs);
            font-weight: 600;
            color: var(--gray-600);
            margin-bottom: var(--space-2);
            display: block;
        }
        .filter-select {
            width: 100%;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 7px 10px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-700);
            outline: none;
            cursor: pointer;
            transition: var(--transition);
        }
        .filter-select:focus { border-color: var(--brand-400); background: #fff; }
        .filter-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-apply {
            width: 100%;
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px;
            font-size: var(--text-sm);
            font-weight: 600;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
        }
        .btn-apply:hover { background: var(--brand-700); }
        .btn-reset {
            width: 100%;
            background: transparent;
            color: var(--gray-400);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 8px;
            font-size: var(--text-xs);
            font-family: var(--font);
            cursor: pointer;
            margin-top: var(--space-2);
            transition: var(--transition);
        }
        .btn-reset:hover { color: var(--gray-600); border-color: var(--gray-300); }

        /* ============================================
           RESULTS PANEL
           ============================================ */
        .results-panel { width: 340px; flex-shrink: 0; }
        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-3);
            padding: 0 2px;
        }
        .results-count { font-size: var(--text-sm); color: var(--gray-400); }
        .results-count strong { color: var(--brand-600); font-weight: 700; }
        .results-list {
            max-height: 680px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: var(--gray-200) transparent;
        }

        /* ============================================
           COMPANY CARD
           ============================================ */
        .company-card {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-md);
            padding: var(--space-4);
            margin-bottom: var(--space-2);
            cursor: pointer;
            transition: var(--transition);
        }
        .company-card:hover {
            border-color: var(--brand-300);
            box-shadow: var(--shadow-md);
            transform: translateY(-1px);
        }
        .company-card-top { display: flex; align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-2); }
        .company-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            min-width: 22px;
            background: var(--brand-600);
            color: #fff;
            border-radius: 5px;
            font-size: 0.65rem;
            font-weight: 700;
            margin-top: 1px;
        }
        .company-name { font-size: var(--text-base); font-weight: 600; color: var(--gray-800); line-height: 1.3; }
        .company-meta { font-size: var(--text-xs); color: var(--gray-400); margin-bottom: var(--space-2); padding-left: 34px; display: flex; align-items: center; gap: 4px; }
        .company-tags { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 34px; }
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.2px;
        }
        .tag-blue { background: var(--brand-50); color: var(--brand-700); border: 1px solid var(--brand-100); }
        .tag-green { background: var(--green-50); color: var(--green-600); border: 1px solid #bbf7d0; }
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #fed7aa; }

        /* ============================================
           MAP
           ============================================ */
        .map-panel { flex: 1; min-width: 0; }
        #kaart {
            height: 720px;
            border-radius: var(--radius-lg);
            border: 1px solid var(--gray-200);
            box-shadow: var(--shadow-sm);
        }

        /* ============================================
           DETAIL DRAWER
           ============================================ */
        .overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15,23,42,0.35);
            z-index: 9999;
            backdrop-filter: blur(3px);
        }
        .drawer {
            position: fixed;
            top: 0;
            right: -500px;
            width: 460px;
            height: 100vh;
            background: #fff;
            border-left: 1px solid var(--gray-200);
            box-shadow: var(--shadow-xl);
            z-index: 10000;
            overflow-y: auto;
            transition: right 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .drawer.open { right: 0; }
        .drawer-header {
            padding: var(--space-6) var(--space-6) var(--space-4);
            border-bottom: 1px solid var(--gray-100);
            position: sticky;
            top: 0;
            background: #fff;
            z-index: 1;
        }
        .drawer-close {
            position: absolute;
            top: var(--space-4);
            right: var(--space-4);
            width: 28px;
            height: 28px;
            background: var(--gray-100);
            border: none;
            border-radius: var(--radius-sm);
            color: var(--gray-500);
            cursor: pointer;
            font-size: 0.9em;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }
        .drawer-close:hover { background: var(--gray-200); color: var(--gray-800); }
        .drawer-company-name { font-size: var(--text-xl); font-weight: 700; color: var(--gray-900); margin-bottom: 4px; padding-right: 36px; }
        .drawer-company-loc { font-size: var(--text-sm); color: var(--gray-400); }
        .drawer-body { padding: var(--space-5) var(--space-6); }
        .drawer-section { margin-bottom: var(--space-5); }
        .drawer-section-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-3);
        }
        .drawer-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--space-2) 0;
            border-bottom: 1px solid var(--gray-50);
        }
        .drawer-row:last-child { border-bottom: none; }
        .drawer-row-label { font-size: var(--text-sm); color: var(--gray-400); font-weight: 500; }
        .drawer-row-value { font-size: var(--text-sm); color: var(--gray-700); font-weight: 500; text-align: right; }
        .drawer-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-website {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--brand-600);
            color: #fff;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
            margin-right: var(--space-2);
        }
        .btn-website:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }
        .btn-enf {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--gray-100);
            color: var(--gray-600);
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
        }
        .btn-enf:hover { background: var(--gray-200); color: var(--gray-800); }
        .score-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            font-size: var(--text-sm);
            font-weight: 800;
        }
        .score-high { background: var(--green-50); color: var(--green-600); }
        .score-mid { background: var(--orange-50); color: var(--orange-600); }

        /* ============================================
           WELCOME STATE
           ============================================ */
        .welcome-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: var(--space-16);
            text-align: center;
        }
        .welcome-icon { font-size: 3em; margin-bottom: var(--space-4); }
        .welcome-title { font-size: var(--text-2xl); font-weight: 700; color: var(--gray-800); margin-bottom: var(--space-2); }
        .welcome-sub { font-size: var(--text-base); color: var(--gray-400); max-width: 400px; }
    </style>
</head>
<body>

<div class="ai-search-box">
  <input type="text" id="aiSearchInput" placeholder="Bijv. papierbedrijven in Duitsland met meer dan 50 werknemers" />
  <button id="aiSearchButton">Zoeken</button>
</div>
<div id="aiSearchResults"></div>
<script>
  const input = document.getElementById('aiSearchInput');
  const button = document.getElementById('aiSearchButton');
  const resultsDiv = document.getElementById('aiSearchResults');
  async function aiSearch(query) {
    const res = await fetch('/api/ai-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    return await res.json();
  }
  async function handleSearch() {
    const query = input.value.trim();
    if (!query) return;
    resultsDiv.innerHTML = '<p>Zoeken...</p>';
    try {
      const data = await aiSearch(query);
      if (data.error) {
        resultsDiv.innerHTML = `<p>Fout: ${data.error}</p>`;
        return;
      }
      let html = `<p>${data.total} resultaten gevonden</p>`;
      data.results.forEach(company => {
        html += `<div class="company-card"><h3>${company.naam}</h3><p>${company.land || ''} - ${company.regio || ''}</p></div>`;
      });
      resultsDiv.innerHTML = html;
    } catch (err) {
      resultsDiv.innerHTML = '<p>Er ging iets mis.</p>';
      console.error(err);
    }
  }
  button.addEventListener('click', handleSearch);
  input.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSearch(); });
</script>

<!-- NAVBAR -->
<nav class="navbar">
    <a href="/" class="navbar-logo">Recycle<em>Find</em></a>
    <div class="navbar-divider"></div>
    <span class="navbar-stat"><strong>{{ totaal }}</strong> companies · <strong>{{ landen|length }}</strong> countries</span>
    <div class="navbar-right">
        <a href="#" class="btn-nav btn-nav-ghost">Sign in</a>
        <a href="#" class="btn-nav btn-nav-primary">Get started</a>
    </div>
</nav>

<!-- HERO -->
<section class="hero">
    <div class="hero-content">
        <div class="hero-badge">🌍 Global Recycling Intelligence Platform</div>
        <h1>Find the right<br><em>recycling partners</em><br>worldwide</h1>
        <p class="hero-sub">Search {{ totaal }} verified companies across {{ landen|length }} countries with AI-powered filters</p>
        <form method="POST" id="searchForm">
            <div class="search-container">
                <div class="search-row">
                    <input class="search-input" name="zoekterm" placeholder="🔍  Search company name..." value="{{ zoekterm }}">
                    <select class="search-select" name="land" id="landSelect" onchange="updateRegio()">
                        <option value="">All Countries</option>
                        {% for l in landen %}
                        <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                        {% endfor %}
                    </select>
                    <select class="search-select" name="regio" id="regioSelect">
                        <option value="">All Regions</option>
                        {% if land and land in regio_per_land %}
                        {% for r in regio_per_land[land] %}
                        <option value="{{ r }}" {% if regio == r %}selected{% endif %}>{{ r }}</option>
                        {% endfor %}
                        {% endif %}
                    </select>
                    <button type="submit" class="btn-search">Search →</button>
                </div>
            </div>
        </form>
    </div>
</section>

<!-- STATS BAR -->
<div class="stats-bar">
    <div class="stat">
        <div class="stat-num">{{ totaal }}</div>
        <div class="stat-label">Companies</div>
    </div>
    <div class="stat">
        <div class="stat-num">{{ landen|length }}</div>
        <div class="stat-label">Countries</div>
    </div>
    <div class="stat">
        <div class="stat-num">Free</div>
        <div class="stat-label">To Search</div>
    </div>
    <div class="stat">
        <div class="stat-num">Live</div>
        <div class="stat-label">Data</div>
    </div>
</div>

<!-- MAIN -->
<div class="main">

    {% if bedrijven %}
    <!-- FILTERS -->
    <form method="POST" id="filterForm">
        <input type="hidden" name="zoekterm" value="{{ zoekterm }}">
        <input type="hidden" name="land" value="{{ land }}">
        <input type="hidden" name="regio" value="{{ regio }}">
        <aside class="filters-panel">
            <div class="filters-title">Filters</div>

            <div class="filter-group">
                <label class="filter-label">Customer Type</label>
                <select class="filter-select" name="klanttype">
                    <option value="">All types</option>
                    <option value="Commercial" {% if klanttype == "Commercial" %}selected{% endif %}>Commercial</option>
                    <option value="Industrial" {% if klanttype == "Industrial" %}selected{% endif %}>Industrial</option>
                    <option value="Residential" {% if klanttype == "Residential" %}selected{% endif %}>Residential</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Material</label>
                <select class="filter-select" name="materiaal">
                    <option value="">All materials</option>
                    <option value="Paper" {% if materiaal == "Paper" %}selected{% endif %}>Paper</option>
                    <option value="Plastic" {% if materiaal == "Plastic" %}selected{% endif %}>Plastic</option>
                    <option value="Metal" {% if materiaal == "Metal" %}selected{% endif %}>Metal</option>
                    <option value="Glass" {% if materiaal == "Glass" %}selected{% endif %}>Glass</option>
                    <option value="Wood" {% if materiaal == "Wood" %}selected{% endif %}>Wood</option>
                    <option value="Electronic" {% if materiaal == "Electronic" %}selected{% endif %}>Electronic</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Annual Volume</label>
                <select class="filter-select" name="volume_filter">
                    <option value="">Any volume</option>
                    <option value="small">Under 1,000 t/y</option>
                    <option value="medium">1,000 – 10,000 t/y</option>
                    <option value="large">Over 10,000 t/y</option>
                </select>
            </div>

            <hr class="filter-divider">
            <button type="submit" class="btn-apply">Apply Filters</button>
            <a href="/" class="btn-reset" style="display:block;text-align:center;text-decoration:none;margin-top:6px;padding:8px;font-size:var(--text-xs);color:var(--gray-400);">Reset all</a>
        </aside>
    </form>

    <!-- RESULTS -->
    <div class="results-panel">
        <div class="results-header">
            <div class="results-count">
                <strong>{{ bedrijven|length }}</strong> of <strong>{{ totaal_gevonden }}</strong> results
            </div>
        </div>
        <div class="results-list">
            {% for bedrijf in bedrijven %}
            <div class="company-card"
                onclick="openDrawer('{{ bedrijf.naam|replace("'","&#39;") }}', '{{ bedrijf.regio }}', '{{ bedrijf.land }}', '{{ bedrijf.url }}', '{{ bedrijf.klanttype }}', '{{ bedrijf.materialen }}', '{{ bedrijf.volume }}', {{ bedrijf.lat }}, {{ bedrijf.lon }})">
                <div class="company-card-top">
                    <span class="company-index">{{ loop.index }}</span>
                    <span class="company-name">{{ bedrijf.naam }}</span>
                </div>
                <div class="company-meta">📍 {{ bedrijf.regio }}, {{ bedrijf.land }}</div>
                <div class="company-tags">
                    {% if bedrijf.klanttype %}{% for t in bedrijf.klanttype.split(",")[:2] %}<span class="tag tag-blue">{{ t.strip() }}</span>{% endfor %}{% endif %}
                    {% if bedrijf.materialen %}{% for m in bedrijf.materialen.split(",")[:2] %}<span class="tag tag-green">{{ m.strip() }}</span>{% endfor %}{% endif %}
                    {% if bedrijf.volume %}<span class="tag tag-orange">{{ bedrijf.volume }} t/y</span>{% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <!-- MAP -->
    <div class="map-panel">
        <div id="kaart"></div>
    </div>

    {% else %}
    <div class="welcome-state">
        <div class="welcome-icon">🔍</div>
        <div class="welcome-title">Search for recycling companies</div>
        <div class="welcome-sub">Use the search bar or filters above to find companies across {{ landen|length }} countries</div>
    </div>
    {% endif %}

</div>

<!-- DETAIL DRAWER -->
<div class="overlay" id="overlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
    <div class="drawer-header">
        <button class="drawer-close" onclick="closeDrawer()">✕</button>
        <div class="drawer-company-name" id="drawerName"></div>
        <div class="drawer-company-loc" id="drawerLoc"></div>
    </div>
    <div class="drawer-body" id="drawerBody"></div>
</div>

<script>
var regioPer = {{ regio_per_land|tojson }};

function updateRegio() {
    var land = document.getElementById("landSelect").value;
    var sel = document.getElementById("regioSelect");
    sel.innerHTML = "<option value=''>All Regions</option>";
    if (land && regioPer[land]) {
        regioPer[land].forEach(function(r) {
            var o = document.createElement("option");
            o.value = r; o.text = r;
            sel.appendChild(o);
        });
    }
}

{% if bedrijven %}
var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"}).addTo(kaart);
var clusterGroep = L.markerClusterGroup();
{% for b in bedrijven %}
L.marker([{{ b.lat }}, {{ b.lon }}])
    .bindPopup("<b>{{ b.naam|replace('"','') }}</b><br><small>{{ b.regio }}, {{ b.land }}</small>")
    .on("click", function(){ openDrawer("{{ b.naam|replace("'","&#39;") }}","{{ b.regio }}","{{ b.land }}","{{ b.url }}","{{ b.klanttype }}","{{ b.materialen }}","{{ b.volume }}",{{ b.lat }},{{ b.lon }}); })
    .addTo(clusterGroep);
{% endfor %}
kaart.addLayer(clusterGroep);
{% endif %}

function openDrawer(naam, regio, land, url, klanttype, materialen, volume, lat, lon) {
window.currentDrawerData = {naam: naam, land: land, klanttype: klanttype, materialen: materialen, volume: volume};
    {% if bedrijven %}kaart.flyTo([lat,lon], 12);{% endif %}
    document.getElementById("drawerName").textContent = naam;
    document.getElementById("drawerLoc").textContent = "📍 " + regio + ", " + land;
    document.getElementById("drawerBody").innerHTML = `
        <div class="drawer-section">
            <div class="drawer-section-title">Company Info</div>
            <div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value">
    <select id="statusSelect" onchange="wijzigStatus()" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
        <option value="">Geen status</option>
        <option value="klant">🟢 Klant</option>
        <option value="potentie">🟡 Potentie</option>
        <option value="in_proces">🔵 In Proces</option>
        <option value="geen_interesse">⚪ Geen Interesse</option>
    </select>
</span></div>
            <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">${klanttype || "—"}</span></div>
            <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">${materialen || "—"}</span></div>
            <div class="drawer-row"><span class="drawer-row-label">Annual Volume</span><span class="drawer-row-value">${volume ? volume + " t/y" : "—"}</span></div><hr class="drawer-divider">
<div class="drawer-section-title">AI Uitrusting-analyse</div>
<button id="equipmentBtn" onclick="analyseUitrusting()" style="padding:8px 16px;background:#2563eb;color:white;border:none;border-radius:6px;cursor:pointer;">AI Analyseren</button>
<div id="equipmentResults" style="margin-top:12px;"></div>
<hr class="drawer-divider">
<div class="drawer-section-title">Notities</div>
<div id="notitiesLijst" style="margin-bottom:12px;"></div>
<textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:60px;padding:8px;border:1px solid #e2e8f0;border-radius:6px;font-family:inherit;font-size:13px;resize:vertical;"></textarea>
<div style="display:flex;align-items:center;gap:12px;margin-top:8px;">
    <label style="font-size:13px;"><input type="radio" name="notitieType" value="team" checked> Team</label>
    <label style="font-size:13px;"><input type="radio" name="notitieType" value="prive"> Privé</label>
    <button onclick="voegNotitieToe()" style="margin-left:auto;padding:6px 14px;background:#2563eb;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Toevoegen</button>
</div>
        </div>
        <hr class="drawer-divider">
        <div class="drawer-section">
            <div class="drawer-section-title">Contact & Details</div>
            <div style="color:var(--gray-400);font-size:var(--text-sm);padding:var(--space-2) 0;">⏳ Loading details...</div>
        </div>
        <hr class="drawer-divider">
      <a href="${url}" target="_blank" class="btn-enf" style="display:none;">Laden...</a>
    `;
    document.getElementById("overlay").style.display = "block";
    document.getElementById("drawer").classList.add("open");
    laadNotities();
    laadStatus();

    fetch("/details?url=" + encodeURIComponent(url))
        .then(r => r.json())
        .then(data => {
            var contactHTML = "";
            if (data.website) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Website</span><span class="drawer-row-value"><a href="${data.website}" target="_blank" style="color:var(--brand-600);font-weight:600;">${data.website.replace("https://","").replace("http://","").split("/")[0]}</a></span></div>`;
            if (data.telefoon) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Phone</span><span class="drawer-row-value">${data.telefoon}</span></div>`;
            if (data.adres) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Address</span><span class="drawer-row-value">${data.adres}${data.stad?", "+data.stad:""}</span></div>`;
            if (data.medewerkers) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Employees</span><span class="drawer-row-value">${data.medewerkers}</span></div>`;
            if (!contactHTML) contactHTML = `<div style="color:var(--gray-400);font-size:var(--text-sm);">No additional details available</div>`;
            if (data.lat_precies && data.lon_precies) {
                kaart.flyTo([data.lat_precies, data.lon_precies], 17);
                L.marker([data.lat_precies, data.lon_precies]).addTo(kaart)
                    .bindPopup("<b>" + naam + "</b>").openPopup();
            }

            document.getElementById("drawerBody").innerHTML = `
                <div class="drawer-section">
                    <div class="drawer-section-title">Company Info</div>
                    <div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value">
    <select id="statusSelect" onchange="wijzigStatus()" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
        <option value="">Geen status</option>
        <option value="klant">🟢 Klant</option>
        <option value="potentie">🟡 Potentie</option>
        <option value="in_proces">🔵 In Proces</option>
        <option value="geen_interesse">⚪ Geen Interesse</option>
    </select>
</span></div>
                    <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">${klanttype||"—"}</span></div>
                    <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">${materialen||"—"}</span></div>
                    <div class="drawer-row"><span class="drawer-row-label">Annual Volume</span><span class="drawer-row-value">${volume?volume+" t/y":"—"}</span></div>
                    <hr class="drawer-divider">
<div class="drawer-section-title">AI Uitrusting-analyse</div>
<button id="equipmentBtn" onclick="analyseUitrusting()" style="padding:8px 16px;background:#2563eb;color:white;border:none;border-radius:6px;cursor:pointer;">AI Analyseren</button>
<div id="equipmentResults" style="margin-top:12px;"></div>
<hr class="drawer-divider">
<div class="drawer-section-title">Notities</div>
<div id="notitiesLijst" style="margin-bottom:12px;"></div>
<textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:60px;padding:8px;border:1px solid #e2e8f0;border-radius:6px;font-family:inherit;font-size:13px;resize:vertical;"></textarea>
<div style="display:flex;align-items:center;gap:12px;margin-top:8px;">
    <label style="font-size:13px;"><input type="radio" name="notitieType" value="team" checked> Team</label>
    <label style="font-size:13px;"><input type="radio" name="notitieType" value="prive"> Privé</label>
    <button onclick="voegNotitieToe()" style="margin-left:auto;padding:6px 14px;background:#2563eb;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Toevoegen</button>
</div>
                </div>
                <hr class="drawer-divider">
                <div class="drawer-section">
                    <div class="drawer-section-title">Contact & Details</div>
                    ${contactHTML}
                </div>
                <hr class="drawer-divider">
                ${data.website?`<a href="${data.website}" target="_blank" class="btn-website">🌐 Visit Website</a>`:""}
                <a href="${url}" target="_blank" class="btn-enf" style="display:none;">Bron →</a>
            `;
            laadNotities();
            laadStatus();
        });
}

async function analyseUitrusting() {
    const btn = document.getElementById("equipmentBtn");
    const resultsDiv = document.getElementById("equipmentResults");
    btn.disabled = true;
    btn.innerText = "Bezig met analyseren...";
    resultsDiv.innerHTML = "";

    try {
        const res = await fetch('/api/company-analysis', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.currentDrawerData || {})
        });
        const data = await res.json();

        const labels = {
            baler: "Baler",
            mrf: "MRF",
            transfer_station: "Transfer Station",
            loading_ramp: "Loading Ramp",
            weighbridge: "Weighbridge",
            walking_floor: "Walking Floor",
            containers: "Containers",
            shredder: "Shredder",
            sorteerinstallatie: "Sorteerinstallatie"
        };

        let html = "";
        for (const key in labels) {
            const pct = data[key] || 0;
            html += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span>${labels[key]}</span><span>${pct}%</span>
                    </div>
                    <div style="background:#e2e8f0;border-radius:4px;height:6px;overflow:hidden;">
                        <div style="background:#2563eb;height:100%;width:${pct}%;"></div>
                    </div>
                </div>`;
        }
        resultsDiv.innerHTML = html;

    } catch (err) {
        resultsDiv.innerHTML = "<p>Er ging iets mis bij de analyse.</p>";
        console.error(err);
    }

    btn.disabled = false;
    btn.innerText = "AI Analyseren";
}
async function laadNotities() {
    const bedrijf = window.currentDrawerData.naam;
    const lijstDiv = document.getElementById("notitiesLijst");
    if (!lijstDiv) return;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";
    try {
        const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(bedrijf));
        const notities = await res.json();
        if (notities.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen notities.</p>";
            return;
        }
        let html = "";
        notities.forEach(n => {
            const badge = n.type === "team" ? "🟢 Team" : "🔒 Privé";
            html += `
                <div style="background:#f8fafc;border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px;">
                    <div style="color:#334155;">${n.tekst}</div>
                    <div style="color:#94a3b8;font-size:11px;margin-top:4px;">${badge} · ${n.timestamp}</div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon notities niet laden.</p>";
    }
}

async function voegNotitieToe() {
    const input = document.getElementById("notitieInput");
    const tekst = input.value.trim();
    if (!tekst) return;
    const type_ = document.querySelector('input[name="notitieType"]:checked').value;
    const bedrijf = window.currentDrawerData.naam;

    try {
        await fetch("/api/notities", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, tekst: tekst, type: type_})
        });
        input.value = "";
        laadNotities();
    } catch (err) {
        alert("Er ging iets mis bij het opslaan.");
    }
}
async function laadStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    if (!select) return;
    try {
        const res = await fetch("/api/status?bedrijf=" + encodeURIComponent(bedrijf));
        const data = await res.json();
        select.value = data.status || "";
    } catch (err) {
        console.error(err);
    }
}

async function wijzigStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    const nieuweStatus = select.value;
    try {
        await fetch("/api/status", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, status: nieuweStatus})
        });
    } catch (err) {
        alert("Er ging iets mis bij het opslaan van de status.");
    }
}
function closeDrawer() {
    document.getElementById("overlay").style.display = "none";
    document.getElementById("drawer").classList.remove("open");
}
</script>

</body>
</html>
'''

LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Inloggen — RecycleFind</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: -apple-system, sans-serif; background: #1e3a8a; height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; }
        .box { background: white; padding: 40px; border-radius: 14px; width: 320px; box-shadow: 0 16px 48px rgba(0,0,0,0.2); }
        h1 { font-size: 20px; margin-bottom: 20px; color: #1e293b; }
        input { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 14px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
        .fout { color: #ef4444; font-size: 13px; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="box">
        <h1>RecycleFind — Inloggen</h1>
        {% if fout %}<div class="fout">{{ fout }}</div>{% endif %}
        <form method="POST">
            <input type="text" name="gebruikersnaam" placeholder="Gebruikersnaam" required>
            <input type="password" name="wachtwoord" placeholder="Wachtwoord" required>
            <button type="submit">Inloggen</button>
        </form>
    </div>
</body>
</html>
'''

@app.route("/login", methods=["GET", "POST"])
def login():
    fout = None
    if request.method == "POST":
        gebruikersnaam = request.form.get("gebruikersnaam", "")
        wachtwoord = request.form.get("wachtwoord", "")
        users = laad_users()
        if gebruikersnaam in users and check_password_hash(users[gebruikersnaam], wachtwoord):
            session["ingelogd"] = True
            session["gebruikersnaam"] = gebruikersnaam
            return redirect(url_for("index"))
        else:
            fout = "Onjuiste gebruikersnaam of wachtwoord."
    return render_template_string(LOGIN_HTML, fout=fout)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/details")
def details():
    url = request.args.get("url", "")
    if not url or "enfpaper" not in url:
        return jsonify({})
    return jsonify(haal_bedrijf_details(url))

@app.route("/api/ai-search", methods=["POST"])
def ai_search():
    from ai_filter import parse_search_query, apply_filters

    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Geen zoekopdracht opgegeven"}), 400

    filters = parse_search_query(query)
    results = apply_filters(ENF_BEDRIJVEN, filters)

    return jsonify({
        "results": results[:200],
        "total": len(results),
        "detected_filters": filters,
    })
@app.route("/api/status", methods=["GET"])
def get_status():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_status()
    return jsonify({"status": alle.get(bedrijf, "")})

@app.route("/api/status", methods=["POST"])
def set_status():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    nieuwe_status = data.get("status", "")
    if not bedrijf:
        return jsonify({"error": "Bedrijf is verplicht"}), 400
    alle = laad_status()
    alle[bedrijf] = nieuwe_status
    bewaar_status(alle)
    return jsonify({"status": nieuwe_status})
@app.route("/api/notities", methods=["GET"])
def get_notities():
    bedrijf = request.args.get("bedrijf", "")
    user_id = get_user_id()
    alle = laad_notities()
    lijst = alle.get(bedrijf, [])
    zichtbaar = [n for n in lijst if n["type"] == "team" or n["user_id"] == user_id]
    return jsonify(zichtbaar)

@app.route("/api/notities", methods=["POST"])
def add_notitie():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    tekst = data.get("tekst", "").strip()
    type_ = data.get("type", "team")
    user_id = get_user_id()

    if not bedrijf or not tekst:
        return jsonify({"error": "Bedrijf en tekst zijn verplicht"}), 400

    alle = laad_notities()
    if bedrijf not in alle:
        alle[bedrijf] = []

    nieuwe_notitie = {
        "tekst": tekst,
        "type": type_,
        "user_id": user_id,
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    alle[bedrijf].append(nieuwe_notitie)
    bewaar_notities(alle)

    return jsonify(nieuwe_notitie)
@app.route("/api/company-analysis", methods=["POST"])
def company_analysis():
    from ai_filter import analyseer_uitrusting

    data = request.get_json()
    resultaat = analyseer_uitrusting(data)

    return jsonify(resultaat)

@app.route("/", methods=["GET", "POST"])
def index():
    zoekterm = land = regio = klanttype = materiaal = ""
    bedrijven = []

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land     = request.form.get("land", "")
        regio    = request.form.get("regio", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")

        bedrijven = ENF_BEDRIJVEN
        if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
        if land:      bedrijven = [b for b in bedrijven if b["land"] == land]
        if regio:     bedrijven = [b for b in bedrijven if b["regio"] == regio]
        if klanttype: bedrijven = [b for b in bedrijven if klanttype in b.get("klanttype","")]
        if materiaal: bedrijven = [b for b in bedrijven if materiaal in b.get("materialen","")]

    totaal_gevonden = len(bedrijven)
    bedrijven = bedrijven[:200]

    return render_template_string(HTML,
        bedrijven=bedrijven, zoekterm=zoekterm, land=land, regio=regio,
        klanttype=klanttype, materiaal=materiaal,
        totaal=len(ENF_BEDRIJVEN), landen=LANDEN,
        totaal_gevonden=totaal_gevonden, regio_per_land=REGIO_PER_LAND)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))