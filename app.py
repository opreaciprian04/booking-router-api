from flask import Flask, request, jsonify
import math
import os
from collections import defaultdict

app = Flask(__name__)

# ==================================================
# CONFIG
# ==================================================

TIMISOARA = {
    "name": "Timisoara Hub",
    "lat": 45.7489,
    "lng": 21.2087
}

MAX_SEATS = 8

# ==================================================
# HELPERS
# ==================================================

def num(v, default=0):
    try:
        return float(v)
    except:
        return default


def haversine(lat1, lon1, lat2, lon2):
    R = 6371

    lat1 = num(lat1)
    lon1 = num(lon1)
    lat2 = num(lat2)
    lon2 = num(lon2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def seats_of(p):
    try:
        s = int(p.get("seats", 1))
        if s < 1:
            return 1
        if s > MAX_SEATS:
            return MAX_SEATS
        return s
    except:
        return 1


def country_from_address(address):
    txt = str(address).lower()

    mapping = {
        "Germany": ["germany", "deutschland"],
        "Italy": ["italy", "italia"],
        "Belgium": ["belgium", "belgia"],
        "Netherlands": ["netherlands", "holland"],
        "Austria": ["austria"],
        "France": ["france"],
        "Spain": ["spain", "espana"],
        "Romania": ["romania"]
    }

    for country, words in mapping.items():
        for w in words:
            if w in txt:
                return country

    return "Other"


def pickup_distance_to_hub(p):
    return haversine(
        p.get("pickup_lat"),
        p.get("pickup_lng"),
        TIMISOARA["lat"],
        TIMISOARA["lng"]
    )


def destination_distance_from_hub(p):
    return haversine(
        TIMISOARA["lat"],
        TIMISOARA["lng"],
        p.get("destination_lat"),
        p.get("destination_lng")
    )


# ==================================================
# STAGE 1
# Pickup -> Timisoara
# ==================================================

def build_stage1(passengers):
    vans = []
    van_id = 1

    remaining = passengers[:]

    while remaining:
        van = []
        seats = 0

        # start din cel mai îndepărtat
        current = max(remaining, key=nearest_to_hub)
        van.append(current)
        seats += int(current.get("seats", 1))
        remaining.remove(current)

        while remaining:
            last = van[-1]

            next_p = min(
                remaining,
                key=lambda x: haversine(
                    last["pickup_lat"],
                    last["pickup_lng"],
                    x["pickup_lat"],
                    x["pickup_lng"]
                )
            )

            if seats + int(next_p.get("seats", 1)) > MAX_SEATS:
                break

            van.append(next_p)
            seats += int(next_p.get("seats", 1))
            remaining.remove(next_p)

        route = [p["pickup_address"] for p in van]
        route.append("Timisoara Hub")

        vans.append({
            "vehicle": f"RO-{van_id}",
            "route": route,
            "passengers": van,
            "used_seats": seats,
            "free_seats": MAX_SEATS - seats,
            "passengers_count": len(van)
        })

        van_id += 1

    return vans


# ==================================================
# STAGE 2
# Timisoara -> Destinations
# ==================================================

def build_stage2(passengers):
    vans = []
    van_id = 1

    grouped = defaultdict(list)

    for p in passengers:
        grouped[country_from_address(p["destination_address"])].append(p)

    for country, plist in grouped.items():

        remaining = plist[:]

        while remaining:
            van = []
            seats = 0

            current = min(
                remaining,
                key=lambda x: destination_distance_from_hub(x)
            )

            van.append(current)
            seats += int(current.get("seats", 1))
            remaining.remove(current)

            while remaining:
                last = van[-1]

                next_p = min(
                    remaining,
                    key=lambda x: haversine(
                        last["destination_lat"],
                        last["destination_lng"],
                        x["destination_lat"],
                        x["destination_lng"]
                    )
                )

                if seats + int(next_p.get("seats", 1)) > MAX_SEATS:
                    break

                van.append(next_p)
                seats += int(next_p.get("seats", 1))
                remaining.remove(next_p)

            route = ["Timisoara Hub"] + [p["destination_address"] for p in van]

            vans.append({
                "vehicle": f"EU-{van_id}",
                "country": country,
                "route": route,
                "passengers": van,
                "used_seats": seats,
                "free_seats": MAX_SEATS - seats,
                "passengers_count": len(van)
            })

            van_id += 1

    return vans

# ==================================================
# ROUTES
# ==================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "Romania Pickup Optimizer V2"
    })


@app.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({
        "ok": True,
        "method": request.method,
        "message": "API works"
    })


@app.route("/optimize", methods=["POST"])
def optimize():
    try:
        data = request.get_json(force=True, silent=True) or {}

        bookings = data.get("bookings", [])

        if not isinstance(bookings, list):
            return jsonify({
                "success": False,
                "error": "bookings must be array"
            }), 400

        stage1 = build_stage1(bookings)
        stage2 = build_stage2(bookings)

        return jsonify({
            "success": True,
            "hub": "Timisoara",
            "total_bookings": len(bookings),
            "stage1_pickup_to_hub": stage1,
            "stage2_hub_to_destination": stage2
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
