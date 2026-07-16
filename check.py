import json

data = json.load(open('bedrijven.json', encoding='utf-8'))

per_land = {}
for b in data:
    land = b['land']
    per_land[land] = per_land.get(land, 0) + 1

print("Bedrijven per land:")
for l, n in sorted(per_land.items()):
    print(f"{l}: {n}")

print(f"\nTotaal: {len(data)} bedrijven")