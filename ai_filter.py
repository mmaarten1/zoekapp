import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """Je bent een filter-extractor voor een recycling bedrijven zoekmachine.
Vertaal de zoekopdracht van de gebruiker naar een JSON object met deze velden
(laat een veld weg als het niet van toepassing is):

- land: land (Engels, zoals in de data, bv. "United Kingdom", "Germany")
- materiaal: "Plastic" | "Paper" | "Glass" | "Metal"
- klanttype: "Residential" | "Commercial"
- min_medewerkers: getal
- min_volume: getal (jaarlijks volume)
- keyword: vrij zoekwoord voor bedrijfsnaam

Antwoord ALLEEN met geldige JSON, geen uitleg, geen markdown."""


def parse_search_query(user_query: str) -> dict:
    """
    Zet een vrije-tekst zoekopdracht om naar gestructureerde filters.
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_query}],
        )

        raw_text = response.content[0].text.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        filters = json.loads(raw_text)
        return filters

    except json.JSONDecodeError:
        print(f"Kon AI-response niet parsen als JSON: {raw_text}")
        return {}
    except Exception as e:
        print(f"AI filter error: {e}")
        return {}


def apply_filters(bedrijven: list, filters: dict) -> list:
    """
    Past de geëxtraheerde filters toe op de lijst bedrijven uit bedrijven.json.
    Velden in de data: naam, url, regio, land, klanttype, materialen, medewerkers, volume.
    """
    results = bedrijven

    if filters.get("land"):
        l = filters["land"].lower()
        results = [b for b in results if l in (b.get("land") or "").lower()]

    if filters.get("materiaal"):
        m = filters["materiaal"].lower()
        results = [b for b in results if m in (b.get("materialen") or "").lower()]

    if filters.get("klanttype"):
        kt = filters["klanttype"].lower()
        results = [b for b in results if kt in (b.get("klanttype") or "").lower()]

    if filters.get("min_medewerkers"):
        def get_medewerkers(b):
            val = b.get("medewerkers", "")
            digits = "".join(c for c in str(val) if c.isdigit())
            return int(digits) if digits else 0
        results = [b for b in results if get_medewerkers(b) >= filters["min_medewerkers"]]

    if filters.get("min_volume"):
        def get_volume(b):
            val = b.get("volume", "")
            digits = "".join(c for c in str(val) if c.isdigit())
            return int(digits) if digits else 0
        results = [b for b in results if get_volume(b) >= filters["min_volume"]]

    if filters.get("keyword"):
        kw = filters["keyword"].lower()
        results = [b for b in results if kw in (b.get("naam") or "").lower()]

    return results