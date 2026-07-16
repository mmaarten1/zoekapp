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
    <title>Papierrecycling Zoekapp</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Segoe UI, Arial; background: #f0f4f8; }
        .header { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 30px 20px; text-align: center; }
        .header h1 { font-size: 2em; margin-bottom: 5px; }
        .header p { opacity: 0.8; }
        .zoekbalk { background: white; padding: 20px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .zoekbalk input, .zoekbalk select { padding: 10px 15px; border: 2px solid #e0e0e0; border-radius: 25px; font-size: 0.9em; outline: none; }
        .zoekbalk input:focus, .zoekbalk select:focus { border-color: #1a73e8; }
        .zoekbalk button { padding: 10px 25px; background: #1a73e8; color: white; border: none; border-radius: 25px; font-size: 0.9em; cursor: pointer; }
        .inhoud { max-width: 1300px; margin: 20px auto; padding: 0 20px; display: flex; gap: 20px; }
        .lijst { flex: 1; max-height: 600px; overflow-y: auto; }
        .kaart-container { flex: 1.2; }
        #kaart { height: 600px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .stats { background: #1a73e8; color: white; padding: 12px 20px; border-radius: 10px; margin-bottom: 15px; }
        .bedrijf { background: white; padding: 12px 15px; margin: 8px 0; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid #1a73e8; cursor: pointer; transition: transform 0.2s; }
        .bedrijf:hover { transform: translateX(5px); background: #e8f0fe; }
        .bedrijf h3 { color: #1a73e8; margin-bottom: 4px; font-size: 0.95em; }
        .bedrijf p { color: #666; font-size: 0.8em; }
        .tag { display: inline-block; background: #e8f0fe; color: #1a73e8; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; margin: 2px; }
        .nummer { display: inline-block; background: #1a73e8; color: white; width: 24px; height: 24px; border-radius: 50%; text-align: center; line-height: 24px; margin-right: 6px; font-size: 0.8em; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Papierrecycling Zoekapp</h1>
        <p>{{ totaal }} bedrijven in {{ landen|length }} landen</p>
    </div>
    <div class="zoekbalk">
        <form method="POST" style="display:flex; gap:10px; flex-wrap:wrap; justify-content:center;">
            <input name="zoekterm" placeholder="Zoek op naam..." value="{{ zoekterm }}" style="width:180px;">
            <select name="land">
                <option value="">Alle landen</option>
                {% for l in landen %}
                <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                {% endfor %}
            </select>
            <select name="klanttype">
                <option value="">Alle klanttypes</option>
                <option value="Commercial" {% if klanttype == "Commercial" %}selected{% endif %}>Commercial</option>
                <option value="Industrial" {% if klanttype == "Industrial" %}selected{% endif %}>Industrial</option>
                <option value="Residential" {% if klanttype == "Residential" %}selected{% endif %}>Residential</option>
            </select>
            <select name="materiaal">
                <option value="">Alle materialen</option>
                <option value="Paper" {% if materiaal == "Paper" %}selected{% endif %}>Paper</option>
                <option value="Plastic" {% if materiaal == "Plastic" %}selected{% endif %}>Plastic</option>
                <option value="Metal" {% if materiaal == "Metal" %}selected{% endif %}>Metal</option>
                <option value="Glass" {% if materiaal == "Glass" %}selected{% endif %}>Glass</option>
            </select>
            <button type="submit">🔍 Zoeken</button>
        </form>
    </div>
    <div class="inhoud">
        <div class="lijst">
            {% if bedrijven %}
            <div class="stats">
                📊 {{ bedrijven|length }} bedrijven gevonden
            </div>
            {% for bedrijf in bedrijven %}
            <div class="bedrijf" onclick="flyTo({{ bedrijf.lat }}, {{ bedrijf.lon }})">
                <h3><span class="nummer">{{ loop.index }}</span>{{ bedrijf.naam }}</h3>
                <p>📍 {{ bedrijf.regio }}, {{ bedrijf.land }}</p>
                {% if bedrijf.klanttype %}
                <p>
                {% for type in bedrijf.klanttype.split(",") %}
                <span class="tag">{{ type.strip() }}</span>
                {% endfor %}
                {% if bedrijf.volume %}
                <span class="tag">📦 {{ bedrijf.volume }} ton/jaar</span>
                {% endif %}
                </p>
                {% endif %}
            </div>
            {% endfor %}
            {% else %}
            <p style="padding:20px; color:#666;">Geen bedrijven gevonden.</p>
            {% endif %}
        </div>
        {% if bedrijven %}
        <div class="kaart-container">
            <div id="kaart"></div>
        </div>
        <script>
            var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(kaart);
            {% for bedrijf in bedrijven %}
            L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(kaart).bindPopup("<b>{{ bedrijf.naam }}</b><br>{{ bedrijf.regio }}, {{ bedrijf.land }}");
            {% endfor %}
            function flyTo(lat, lon) { kaart.flyTo([lat, lon], 12); }
        </script>
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
   bedrijven = [:200]

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land = request.form.get("land", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")

        if zoekterm:
            bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
        if land:
            bedrijven = [b for b in bedrijven if b["land"] == land]
        if klanttype:
            bedrijven = [b for b in bedrijven if klanttype in b.get("klanttype", "")]
        if materiaal:
            bedrijven = [b for b in bedrijven if materiaal in b.get("materialen", "")]

    return render_template_string(HTML, bedrijven=bedrijven, zoekterm=zoekterm, land=land, klanttype=klanttype, materiaal=materiaal, totaal=len(ENF_BEDRIJVEN), landen=LANDEN)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))