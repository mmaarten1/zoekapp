import os
from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

def zoek_bedrijven(stad, categorie, extra=""):
    zoekvraag = categorie + " " + extra + " " + stad
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": zoekvraag,
        "format": "json",
        "limit": 10,
        "addressdetails": 1
    }
    headers = {"User-Agent": "zoekapp/1.0"}
    response = requests.get(url, headers=headers, params=params)
    return response.json()

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Zoekapp</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Segoe UI, Arial; background: #f0f4f8; }
        .header { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 40px 20px; text-align: center; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.8; }
        .zoekbalk { background: white; padding: 25px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .zoekbalk input { padding: 12px 20px; width: 200px; border: 2px solid #e0e0e0; border-radius: 25px; font-size: 1em; outline: none; }
        .zoekbalk input:focus { border-color: #1a73e8; }
        .zoekbalk button { padding: 12px 30px; background: #1a73e8; color: white; border: none; border-radius: 25px; font-size: 1em; cursor: pointer; }
        .inhoud { max-width: 1200px; margin: 30px auto; padding: 0 20px; display: flex; gap: 20px; }
        .lijst { flex: 1; }
        .kaart-container { flex: 1; }
        #kaart { height: 500px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .stats { background: #1a73e8; color: white; padding: 15px 25px; border-radius: 10px; margin-bottom: 20px; }
        .bedrijf { background: white; padding: 15px 20px; margin: 10px 0; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid #1a73e8; cursor: pointer; transition: transform 0.2s; }
        .bedrijf:hover { transform: translateX(5px); background: #e8f0fe; }
        .bedrijf h3 { color: #1a73e8; margin-bottom: 5px; font-size: 1em; }
        .bedrijf p { color: #666; font-size: 0.85em; }
        .nummer { display: inline-block; background: #1a73e8; color: white; width: 26px; height: 26px; border-radius: 50%; text-align: center; line-height: 26px; margin-right: 8px; font-size: 0.85em; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Zoekapp</h1>
        <p>Vind bedrijven slim en snel in elke stad</p>
    </div>
    <div class="zoekbalk">
        <form method="POST" style="display:flex; gap:10px; flex-wrap:wrap; justify-content:center;">
            <input name="stad" placeholder="Stad" value="{{ stad }}">
            <input name="categorie" placeholder="Categorie" value="{{ categorie }}">
            <input name="extra" placeholder="Extra filter" value="{{ extra }}">
            <button type="submit">Zoeken</button>
        </form>
    </div>
    <div class="inhoud">
        <div class="lijst">
            {% if bedrijven %}
            <div class="stats">
                {{ bedrijven|length }} resultaten voor {{ categorie }} in {{ stad }}
            </div>
            {% for bedrijf in bedrijven %}
            <div class="bedrijf" onclick="flyTo({{ bedrijf.lat }}, {{ bedrijf.lon }})">
                <h3><span class="nummer">{{ loop.index }}</span>{{ bedrijf.display_name.split(",")[0] }}</h3>
                <p>{{ bedrijf.display_name }}</p>
            </div>
            {% endfor %}
            {% endif %}
        </div>
        {% if bedrijven %}
        <div class="kaart-container">
            <div id="kaart"></div>
        </div>
        <script>
            var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 11);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(kaart);
            {% for bedrijf in bedrijven %}
            L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(kaart).bindPopup("{{ bedrijf.display_name.split(',')[0] }}");
            {% endfor %}
            function flyTo(lat, lon) { kaart.flyTo([lat, lon], 15); }
        </script>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route("/", methods=["GET", "POST"])
def index():
    bedrijven = []
    stad = ""
    categorie = ""
    extra = ""
    if request.method == "POST":
        stad = request.form["stad"]
        categorie = request.form["categorie"]
        extra = request.form.get("extra", "")
        bedrijven = zoek_bedrijven(stad, categorie, extra)
    return render_template_string(HTML, bedrijven=bedrijven, stad=stad, categorie=categorie, extra=extra)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))