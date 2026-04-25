from flask import Flask, jsonify, request
import os
import math

app = Flask(__name__)

MAX_SEATS = 8

TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

# ==========================================
# HELPERS
# ==========================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371

    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing(lat1, lon1, lat2, lon2):
    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.cos(math.radians(lon2 - lon1))
    )

    return (math.degrees(math.atan2(y, x)) + 360) % 360


def zone_from_bearing(b):
    if b < 90:
        return "NE"
    elif b < 180:
        return "SE"
    elif b < 270:
        return "SW"
    return "NW"


# ==========================================
# INPUT JSON
# Grupează TOT ce primește în input
# Nu contează data
# ==========================================

def get_bookings_from_request():
    data = request.get_json(silent=True) or {}

    # dacă vine direct listă
    if isinstance(data, list):
        return data

    # dacă vine {"bookings":[...]}
    if isinstance(data, dict):
        return data.get("bookings", [])

    return []


# ==========================================
# CORE
# ==========================================

def build_groups(rows):
    enriched = []

    for r in rows:

        if not r.get("pickup_lat") or not r.get("pickup_lng"):
            continue

        dist = haversine(
            r["pickup_lat"],
            r["pickup_lng"],
            TIMISOARA["lat"],
            TIMISOARA["lng"]
        )

        brg = bearing(
            TIMISOARA["lat"],
            TIMISOARA["lng"],
            r["pickup_lat"],
            r["pickup_lng"]
        )

        enriched.append({
            **r,
            "distance_km": round(dist, 1),
            "zone": zone_from_bearing(brg)
        })

    zones = {}

    for p in enriched:
        zones.setdefault(p["zone"], []).append(p)

    trips = []
    trip_no = 1

    for zone, people in zones.items():

        people.sort(key=lambda x: x["distance_km"], reverse=True)

        while people:

            bus = []
            seats = 0
            remain = []

            for p in people:
                needed = int(p.get("persons", 1))

                if seats + needed <= MAX_SEATS:
                    bus.append(p)
                    seats += needed
                else:
                    remain.append(p)

            people = remain

            trips.append({
                "trip_id": f"BUS-{trip_no:03}",
                "zone": zone,
                "count_people": seats,
                "bookings": len(bus),
                "passengers": bus
            })

            trip_no += 1

    return trips


# ==========================================
# API
# ==========================================

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Trip Optimizer JSON Mode"
    })


@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        rows = get_bookings_from_request()
        trips = build_groups(rows)

        return jsonify({
            "status": "success",
            "total_received": len(rows),
            "trips_count": len(trips),
            "trips": trips
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))