import os
import json
from flask import Flask, render_template_string, request, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

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
        return details
    except:
        return {}

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>RecycleFind - Global Recycling Intelligence</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: "Inter", sans-serif; background: #f0f4f8; color: #1e293b; min-height: 100vh; }

        /* NAVBAR */
        .navbar {
            background: #fff;
            border-bottom: 1px solid #e2e8f0;
            padding: 0 40px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .logo { font-size: 1.3em; font-weight: 800; color: #1e293b; letter-spacing: -0.5px; }
        .logo span { color: #2563eb; }
        .nav-stat { font-size: 0.82em; color: #94a3b8; }
        .nav-stat strong { color: #2563eb; }

        /* HERO */
        .hero {
            background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 50%, #2563eb 100%);
            padding: 60px 40px 50px;
            text-align: center;
        }
        .hero-badge {
            display: inline-block;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.25);
            color: #fff;
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 0.78em;
            font-weight: 500;
            margin-bottom: 20px;
        }
        .hero h1 {
            font-size: 2.8em;
            font-weight: 800;
            color: #fff;
            margin-bottom: 12px;
            letter-spacing: -1.5px;
            line-height: 1.1;
        }
        .hero h1 span { color: #93c5fd; }
        .hero p { color: rgba(255,255,255,0.8); font-size: 1em; margin-bottom: 36px; }

        /* ZOEKBALK */
        .search-box {
            display: flex;
            gap: 8px;
            justify-content: center;
            flex-wrap: wrap;
            max-width: 950px;
            margin: 0 auto;
        }
        .search-box input, .search-box select {
            padding: 10px 14px;
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            color: #1e293b;
            font-size: 0.86em;
            font-family: "Inter", sans-serif;
            outline: none;
            transition: all 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .search-box input { width: 190px; }
        .search-box select { width: 160px; }
        .search-box input:focus, .search-box select:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
        .search-box input::placeholder { color: #94a3b8; }
        .btn-search {
            padding: 10px 22px;
            background: #fff;
            color: #2563eb;
            border: none;
            border-radius: 8px;
            font-size: 0.86em;
            font-weight: 700;
            cursor: pointer;
            font-family: "Inter", sans-serif;
            transition: all 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .btn-search:hover { background: #eff6ff; transform: translateY(-1px); }

        /* STATS BAR */
        .stats-bar {
            background: #fff;
            border-bottom: 1px solid #e2e8f0;
            padding: 14px 40px;
            display: flex;
            gap: 50px;
            justify-content: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .stat { text-align: center; }
        .stat-num { font-size: 1.4em; font-weight: 700; color: #2563eb; }
        .stat-label { font-size: 0.7em; color: #94a3b8; margin-top: 1px; text-transform: uppercase; letter-spacing: 0.5px; }

        /* MAIN */
        .main {
            max-width: 1400px;
            margin: 24px auto;
            padding: 0 24px;
            display: flex;
            gap: 20px;
        }

        /* RESULTS */
        .results-panel { width: 360px; flex-shrink: 0; }
        .results-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .results-count { font-size: 0.82em; color: #94a3b8; }
        .results-count strong { color: #2563eb; }
        .results-list {
            max-height: 700px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: #cbd5e1 transparent;
        }

        /* BEDRIJFSKAART */
        .company-card {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.15s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .company-card:hover { border-color: #2563eb; box-shadow: 0 4px 12px rgba(37,99,235,0.1); transform: translateY(-1px); }
        .company-num {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 20px;
            height: 20px;
            background: #2563eb;
            color: white;
            border-radius: 4px;
            font-size: 0.7em;
            font-weight: 700;
            margin-right: 8px;
        }
        .company-name {
            font-size: 0.9em;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
        }
        .company-location { font-size: 0.76em; color: #94a3b8; margin-bottom: 7px; padding-left: 28px; }
        .company-tags { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 28px; }
        .tag { padding: 2px 7px; border-radius: 4px; font-size: 0.68em; font-weight: 500; }
        .tag-blue { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
        .tag-green { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
        .tag-orange { background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa; }

        /* KAART */
        .map-panel { flex: 1; }
        #kaart { height: 748px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }

        /* DETAIL PANEL */
        .overlay {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(15,23,42,0.4);
            z-index: 2000;
            backdrop-filter: blur(2px);
        }
        .detail-panel {
            position: fixed;
            right: -500px;
            top: 0;
            width: 440px;
            height: 100vh;
            background: #fff;
            border-left: 1px solid #e2e8f0;
            z-index: 2001;
            overflow-y: auto;
            transition: right 0.3s ease;
            padding: 28px;
            box-shadow: -4px 0 20px rgba(0,0,0,0.08);
        }
        .detail-panel.open { right: 0; }
        .detail-close {
            position: absolute;
            top: 18px; right: 18px;
            background: #f1f5f9;
            border: none;
            color: #64748b;
            width: 30px; height: 30px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1em;
        }
        .detail-close:hover { background: #e2e8f0; color: #1e293b; }
        .detail-title { font-size: 1.2em; font-weight: 700; color: #1e293b; margin-bottom: 4px; padding-right: 36px; }
        .detail-location { color: #94a3b8; font-size: 0.82em; margin-bottom: 18px; }
        .detail-section { margin-bottom: 16px; }
        .detail-label { font-size: 0.68em; text-transform: uppercase; letter-spacing: 0.8px; color: #94a3b8; margin-bottom: 4px; font-weight: 600; }
        .detail-value { font-size: 0.88em; color: #334155; }
        .detail-website {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #2563eb;
            color: white;
            padding: 8px 14px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.82em;
            font-weight: 600;
            margin-top: 8px;
            transition: background 0.2s;
        }
        .detail-website:hover { background: #1d4ed8; }
        .detail-enf {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #f1f5f9;
            color: #64748b;
            padding: 8px 14px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.82em;
            font-weight: 600;
            margin-top: 8px;
            margin-left: 6px;
        }
        .detail-enf:hover { background: #e2e8f0; color: #1e293b; }
        .detail-divider { border: none; border-top: 1px solid #f1f5f9; margin: 14px 0; }

        /* WELKOM */
        .welcome { width: 100%; text-align: center; padding: 80px 20px; }
        .welcome h2 { font-size: 1.4em; color: #1e293b; margin-bottom: 10px; font-weight: 600; }
        .welcome p { color: #94a3b8; font-size: 0.9em; }
    </style>
</head>
<body>

<nav class="navbar">
    <div class="logo">Recycle<span>Find</span></div>
    <div class="nav-stat"><strong>{{ totaal }}</strong> companies · <strong>{{ landen|length }}</strong> countries</div>
</nav>

<div class="hero">
    <div class="hero-badge">🌍 Global Recycling Intelligence</div>
    <h1>Find <span>Recycling</span> Companies Worldwide</h1>
    <p>Search {{ totaal }} verified paper recycling companies across {{ landen|length }} countries</p>
    <form method="POST" id="searchForm">
        <div class="search-box">
            <input name="zoekterm" placeholder="Company name..." value="{{ zoekterm }}">
            <select name="land" id="landSelect" onchange="updateRegio()">
                <option value="">All Countries</option>
                {% for l in landen %}
                <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                {% endfor %}
            </select>
            <select name="regio" id="regioSelect">
                <option value="">All Regions</option>
                {% if land and land in regio_per_land %}
                {% for r in regio_per_land[land] %}
                <option value="{{ r }}" {% if regio == r %}selected{% endif %}>{{ r }}</option>
                {% endfor %}
                {% endif %}
            </select>
            <select name="klanttype">
                <option value="">All Customer Types</option>
                <option value="Commercial" {% if klanttype == "Commercial" %}selected{% endif %}>Commercial</option>
                <option value="Industrial" {% if klanttype == "Industrial" %}selected{% endif %}>Industrial</option>
                <option value="Residential" {% if klanttype == "Residential" %}selected{% endif %}>Residential</option>
            </select>
            <select name="materiaal">
                <option value="">All Materials</option>
                <option value="Paper" {% if materiaal == "Paper" %}selected{% endif %}>Paper</option>
                <option value="Plastic" {% if materiaal == "Plastic" %}selected{% endif %}>Plastic</option>
                <option value="Metal" {% if materiaal == "Metal" %}selected{% endif %}>Metal</option>
                <option value="Glass" {% if materiaal == "Glass" %}selected{% endif %}>Glass</option>
            </select>
            <button type="submit" class="btn-search">🔍 Search</button>
        </div>
    </form>
</div>

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
        <div class="stat-num">100%</div>
        <div class="stat-label">Verified</div>
    </div>
</div>

<div class="main">
    {% if bedrijven %}
    <div class="results-panel">
        <div class="results-meta">
            <div class="results-count">
                <strong>{{ bedrijven|length }}</strong> of <strong>{{ totaal_gevonden }}</strong> results
            </div>
        </div>
        <div class="results-list">
            {% for bedrijf in bedrijven %}
            <div class="company-card"
                onclick="showDetail('{{ bedrijf.naam|replace("'","") }}', '{{ bedrijf.regio }}', '{{ bedrijf.land }}', '{{ bedrijf.url }}', '{{ bedrijf.klanttype }}', '{{ bedrijf.materialen }}', '{{ bedrijf.volume }}', {{ bedrijf.lat }}, {{ bedrijf.lon }})">
                <div class="company-name">
                    <span class="company-num">{{ loop.index }}</span>
                    {{ bedrijf.naam }}
                </div>
                <div class="company-location">📍 {{ bedrijf.regio }}, {{ bedrijf.land }}</div>
                <div class="company-tags">
                    {% if bedrijf.klanttype %}
                    {% for type in bedrijf.klanttype.split(",") %}
                    <span class="tag tag-blue">{{ type.strip() }}</span>
                    {% endfor %}
                    {% endif %}
                    {% if bedrijf.materialen %}
                    {% for mat in bedrijf.materialen.split(",")[:2] %}
                    <span class="tag tag-green">{{ mat.strip() }}</span>
                    {% endfor %}
                    {% endif %}
                    {% if bedrijf.volume %}
                    <span class="tag tag-orange">{{ bedrijf.volume }} t/y</span>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <div class="map-panel">
        <div id="kaart"></div>
    </div>
    {% else %}
    <div class="welcome">
        <h2>Search for Recycling Companies</h2>
        <p>Use the filters above to search {{ totaal }} companies worldwide</p>
    </div>
    {% endif %}
</div>

<div class="overlay" id="overlay" onclick="closeDetail()"></div>
<div class="detail-panel" id="detailPanel">
    <button class="detail-close" onclick="closeDetail()">✕</button>
    <div id="detailContent"></div>
</div>

<script>
var regioPer = {{ regio_per_land|tojson }};

function updateRegio() {
    var land = document.getElementById("landSelect").value;
    var select = document.getElementById("regioSelect");
    select.innerHTML = "<option value=''>All Regions</option>";
    if (land && regioPer[land]) {
        regioPer[land].forEach(function(r) {
            var opt = document.createElement("option");
            opt.value = r;
            opt.text = r;
            select.appendChild(opt);
        });
    }
}

{% if bedrijven %}
var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(kaart);

{% for bedrijf in bedrijven %}
L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}])
    .addTo(kaart)
    .bindPopup("<b>{{ bedrijf.naam|replace('"','') }}</b><br>{{ bedrijf.regio }}, {{ bedrijf.land }}")
    .on("click", function() {
        showDetail("{{ bedrijf.naam|replace("'","") }}", "{{ bedrijf.regio }}", "{{ bedrijf.land }}", "{{ bedrijf.url }}", "{{ bedrijf.klanttype }}", "{{ bedrijf.materialen }}", "{{ bedrijf.volume }}", {{ bedrijf.lat }}, {{ bedrijf.lon }});
    });
{% endfor %}
{% endif %}

function showDetail(naam, regio, land, url, klanttype, materialen, volume, lat, lon) {
    {% if bedrijven %}kaart.flyTo([lat, lon], 12);{% endif %}
    document.getElementById("overlay").style.display = "block";
    document.getElementById("detailPanel").classList.add("open");
    document.getElementById("detailContent").innerHTML = `
        <div class="detail-title">${naam}</div>
        <div class="detail-location">📍 ${regio}, ${land}</div>
        <hr class="detail-divider">
        <div class="detail-section"><div class="detail-label">Customer Type</div><div class="detail-value">${klanttype || "Not specified"}</div></div>
        <div class="detail-section"><div class="detail-label">Materials</div><div class="detail-value">${materialen || "Not specified"}</div></div>
        ${volume ? `<div class="detail-section"><div class="detail-label">Annual Volume</div><div class="detail-value">${volume} tons/year</div></div>` : ""}
        <hr class="detail-divider">
        <div style="color:#94a3b8;font-size:0.82em;">⏳ Loading details...</div>
        <hr class="detail-divider">
        <a href="${url}" target="_blank" class="detail-enf">View on ENF →</a>
    `;
    fetch("/details?url=" + encodeURIComponent(url))
        .then(r => r.json())
        .then(data => {
            var extra = "";
            if (data.website) extra += `<div class="detail-section"><div class="detail-label">Website</div><a href="${data.website}" target="_blank" class="detail-website">🌐 Visit Website</a></div>`;
            if (data.telefoon) extra += `<div class="detail-section"><div class="detail-label">Phone</div><div class="detail-value">${data.telefoon}</div></div>`;
            if (data.medewerkers) extra += `<div class="detail-section"><div class="detail-label">Employees</div><div class="detail-value">${data.medewerkers}</div></div>`;
            if (data.adres) extra += `<div class="detail-section"><div class="detail-label">Address</div><div class="detail-value">${data.adres}${data.stad ? ", "+data.stad : ""}</div></div>`;
            document.getElementById("detailContent").innerHTML = `
                <div class="detail-title">${naam}</div>
                <div class="detail-location">📍 ${regio}, ${land}</div>
                <hr class="detail-divider">
                ${extra || "<div style='color:#94a3b8;font-size:0.82em;'>No additional details available</div>"}
                <hr class="detail-divider">
                <div class="detail-section"><div class="detail-label">Customer Type</div><div class="detail-value">${klanttype || "Not specified"}</div></div>
                <div class="detail-section"><div class="detail-label">Materials</div><div class="detail-value">${materialen || "Not specified"}</div></div>
                ${volume ? `<div class="detail-section"><div class="detail-label">Annual Volume</div><div class="detail-value">${volume} tons/year</div></div>` : ""}
                <hr class="detail-divider">
                <a href="${url}" target="_blank" class="detail-enf">View on ENF →</a>
            `;
        });
}

function closeDetail() {
    document.getElementById("overlay").style.display = "none";
    document.getElementById("detailPanel").classList.remove("open");
}
</script>

</body>
</html>
'''

@app.route("/details")
def details():
    url = request.args.get("url", "")
    if not url or "enfpaper" not in url:
        return jsonify({})
    data = haal_bedrijf_details(url)
    return jsonify(data)

@app.route("/", methods=["GET", "POST"])
def index():
    zoekterm = ""
    land = ""
    regio = ""
    klanttype = ""
    materiaal = ""
    bedrijven = []

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land = request.form.get("land", "")
        regio = request.form.get("regio", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")

        bedrijven = ENF_BEDRIJVEN

        if zoekterm:
            bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
        if land:
            bedrijven = [b for b in bedrijven if b["land"] == land]
        if regio:
            bedrijven = [b for b in bedrijven if b["regio"] == regio]
        if klanttype:
            bedrijven = [b for b in bedrijven if klanttype in b.get("klanttype", "")]
        if materiaal:
            bedrijven = [b for b in bedrijven if materiaal in b.get("materialen", "")]

    totaal_gevonden = len(bedrijven)
    bedrijven = bedrijven[:200]

    return render_template_string(HTML, bedrijven=bedrijven, zoekterm=zoekterm, land=land, regio=regio, klanttype=klanttype, materiaal=materiaal, totaal=len(ENF_BEDRIJVEN), landen=LANDEN, totaal_gevonden=totaal_gevonden, regio_per_land=REGIO_PER_LAND)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))