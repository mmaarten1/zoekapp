import os
import json
from flask import Flask, render_template_string, request

app = Flask(__name__)

with open("bedrijven.json", "r", encoding="utf-8") as f:
    ENF_BEDRIJVEN = json.load(f)

LANDEN = sorted(set(b["land"] for b in ENF_BEDRIJVEN))

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>RecycleFind - Global Recycling Directory</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; background: #0a0f1e; color: #e2e8f0; min-height: 100vh; }

        /* NAVBAR */
        .navbar {
            background: #0d1426;
            border-bottom: 1px solid #1e2d4a;
            padding: 0 40px;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        .logo {
            font-size: 1.4em;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.5px;
        }
        .logo span { color: #3b82f6; }
        .navbar-stats {
            font-size: 0.8em;
            color: #64748b;
        }
        .navbar-stats strong { color: #3b82f6; }

        /* HERO */
        .hero {
            background: linear-gradient(135deg, #0d1426 0%, #0f2044 50%, #0d1426 100%);
            padding: 60px 40px 40px;
            text-align: center;
            border-bottom: 1px solid #1e2d4a;
        }
        .hero h1 {
            font-size: 2.8em;
            font-weight: 700;
            color: #fff;
            margin-bottom: 12px;
            letter-spacing: -1px;
        }
        .hero h1 span { color: #3b82f6; }
        .hero p {
            color: #94a3b8;
            font-size: 1.1em;
            margin-bottom: 40px;
        }

        /* ZOEKBALK */
        .zoekbalk {
            display: flex;
            gap: 10px;
            justify-content: center;
            flex-wrap: wrap;
            max-width: 900px;
            margin: 0 auto;
        }
        .zoekbalk input, .zoekbalk select {
            padding: 12px 18px;
            background: #1e2d4a;
            border: 1px solid #2d3f5e;
            border-radius: 8px;
            color: #e2e8f0;
            font-size: 0.9em;
            font-family: 'Inter', sans-serif;
            outline: none;
            transition: border 0.2s;
        }
        .zoekbalk input { width: 220px; }
        .zoekbalk select { width: 180px; }
        .zoekbalk input:focus, .zoekbalk select:focus {
            border-color: #3b82f6;
        }
        .zoekbalk input::placeholder { color: #64748b; }
        .zoekbalk select option { background: #1e2d4a; }
        .btn-search {
            padding: 12px 28px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 600;
            cursor: pointer;
            font-family: 'Inter', sans-serif;
            transition: background 0.2s;
        }
        .btn-search:hover { background: #2563eb; }

        /* CONTENT */
        .content {
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 30px;
            display: flex;
            gap: 24px;
        }

        /* SIDEBAR */
        .sidebar {
            width: 340px;
            flex-shrink: 0;
        }
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        .results-count {
            font-size: 0.85em;
            color: #64748b;
        }
        .results-count strong { color: #3b82f6; }
        .results-list {
            max-height: 680px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: #2d3f5e #0d1426;
        }
        .bedrijf-card {
            background: #0d1426;
            border: 1px solid #1e2d4a;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .bedrijf-card:hover {
            border-color: #3b82f6;
            background: #111827;
            transform: translateY(-1px);
        }
        .bedrijf-naam {
            font-size: 0.95em;
            font-weight: 600;
            color: #e2e8f0;
            margin-bottom: 6px;
        }
        .bedrijf-locatie {
            font-size: 0.8em;
            color: #64748b;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .tags {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }
        .tag {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 500;
        }
        .tag-blue { background: #1e3a5f; color: #60a5fa; }
        .tag-green { background: #1a3a2a; color: #4ade80; }
        .tag-orange { background: #3a2a0a; color: #fb923c; }
        .nummer {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            background: #3b82f6;
            color: white;
            border-radius: 4px;
            font-size: 0.72em;
            font-weight: 700;
            margin-right: 8px;
        }

        /* KAART */
        .kaart-container { flex: 1; }
        #kaart {
            height: 720px;
            border-radius: 12px;
            border: 1px solid #1e2d4a;
        }

        /* WELKOM */
        .welkom {
            width: 100%;
            text-align: center;
            padding: 80px 20px;
        }
        .welkom h2 { font-size: 1.6em; color: #e2e8f0; margin-bottom: 12px; }
        .welkom p { color: #64748b; font-size: 1em; }

        /* STATS BALK */
        .stats-bar {
            background: #0d1426;
            border-top: 1px solid #1e2d4a;
            border-bottom: 1px solid #1e2d4a;
            padding: 12px 40px;
            display: flex;
            gap: 40px;
            justify-content: center;
        }
        .stat-item { text-align: center; }
        .stat-number { font-size: 1.4em; font-weight: 700; color: #3b82f6; }
        .stat-label { font-size: 0.75em; color: #64748b; margin-top: 2px; }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">Recycle<span>Find</span></div>
        <div class="navbar-stats">
            <strong>{{ totaal }}</strong> bedrijven in <strong>{{ landen|length }}</strong> landen
        </div>
    </nav>

    <div class="hero">
        <h1>Find <span>Recycling</span> Companies Worldwide</h1>
        <p>Search through {{ totaal }} paper recycling companies across {{ landen|length }} countries</p>
        <form method="POST">
            <div class="zoekbalk">
                <input name="zoekterm" placeholder="Search by company name..." value="{{ zoekterm }}">
                <select name="land">
                    <option value="">All Countries</option>
                    {% for l in landen %}
                    <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                    {% endfor %}
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
        <div class="stat-item">
            <div class="stat-number">{{ totaal }}</div>
            <div class="stat-label">Total Companies</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">{{ landen|length }}</div>
            <div class="stat-label">Countries</div>
        </div>
        <div class="stat-item">
            <div class="stat-number">100%</div>
            <div class="stat-label">Verified Data</div>
        </div>
    </div>

    <div class="content">
        {% if bedrijven %}
        <div class="sidebar">
            <div class="results-header">
                <div class="results-count">
                    Showing <strong>{{ bedrijven|length }}</strong> of <strong>{{ totaal_gevonden }}</strong> results
                </div>
            </div>
            <div class="results-list">
                {% for bedrijf in bedrijven %}
                <div class="bedrijf-card" onclick="flyTo({{ bedrijf.lat }}, {{ bedrijf.lon }})">
                    <div class="bedrijf-naam">
                        <span class="nummer">{{ loop.index }}</span>{{ bedrijf.naam }}
                    </div>
                    <div class="bedrijf-locatie">
                        📍 {{ bedrijf.regio }}, {{ bedrijf.land }}
                    </div>
                    <div class="tags">
                        {% if bedrijf.klanttype %}
                        {% for type in bedrijf.klanttype.split(",") %}
                        <span class="tag tag-blue">{{ type.strip() }}</span>
                        {% endfor %}
                        {% endif %}
                        {% if bedrijf.materialen %}
                        {% for mat in bedrijf.materialen.split(",") %}
                        <span class="tag tag-green">{{ mat.strip() }}</span>
                        {% endfor %}
                        {% endif %}
                        {% if bedrijf.volume %}
                        <span class="tag tag-orange">📦 {{ bedrijf.volume }} t/y</span>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        <div class="kaart-container">
            <div id="kaart"></div>
        </div>
        <script>
            var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '© OpenStreetMap'
            }).addTo(kaart);
            {% for bedrijf in bedrijven %}
            L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(kaart).bindPopup(
                "<b>{{ bedrijf.naam }}</b><br>{{ bedrijf.regio }}, {{ bedrijf.land }}<br>{{ bedrijf.klanttype }}"
            );
            {% endfor %}
            function flyTo(lat, lon) { kaart.flyTo([lat, lon], 12); }
        </script>
        {% else %}
        <div class="welkom">
            <h2>Search for Recycling Companies</h2>
            <p>Use the filters above to find paper recycling companies worldwide</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route("/", methods=["GET", "POST"])
def index():
    zoekterm = ""
    land = ""
    klanttype = ""
    materiaal = ""
    bedrijven = []

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land = request.form.get("land", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")

        bedrijven = ENF_BEDRIJVEN

        if zoekterm:
            bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
        if land:
            bedrijven = [b for b in bedrijven if b["land"] == land]
        if klanttype:
            bedrijven = [b for b in bedrijven if klanttype in b.get("klanttype", "")]
        if materiaal:
            bedrijven = [b for b in bedrijven if materiaal in b.get("materialen", "")]

    totaal_gevonden = len(bedrijven)
    bedrijven = bedrijven[:200]

    return render_template_string(HTML, bedrijven=bedrijven, zoekterm=zoekterm, land=land, klanttype=klanttype, materiaal=materiaal, totaal=len(ENF_BEDRIJVEN), landen=LANDEN, totaal_gevonden=totaal_gevonden)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))