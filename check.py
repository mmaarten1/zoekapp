import json

data = json.load(open('bedrijven.json'))

per_land = {}
for b in data:
    land = b['land']
    per_land[land] = per_land.get(land, 0) + 1

print("Bedrijven per land:")
for l, n in sorted(per_land.items()):
    print(f"{l}: {n}")

met_coords = len([b for b in data if b.get('lat')])
zonder_coords = len([b for b in data if not b.get('lat')])
print(f"\nMet coordinaten: {met_coords}")
print(f"Zonder coordinaten: {zonder_coords}")