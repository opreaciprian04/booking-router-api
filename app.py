from flask import Flask, request, jsonify
import math
import os
import traceback
from collections import defaultdict

# ==================================================
# APP
# ==================================================

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

def to_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default


def to_int(value, default=1):
    try:
        return int(value)
    except:
        return default


def haversine(lat1, lon1, lat2, lon2):
    """
    Distance in KM
    """
    R = 6371

    lat1 = to_float(lat1)
    lon1 = to_float(lon1)
    lat2 = to_float(lat2)
    lon2 = to_float(lon2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def seats_of(passenger):
    seats = to_int(passenger.get("locuri", passenger.get("seats", 1)), 1)

    if seats < 1:
        return 1

    if seats > MAX_SEATS:
        return MAX_SEATS

    return seats


def detect_country(address):
    text = str(address).lower()

    countries = {
        "Germania": ["germany", "deutschland", "germania"],
        "Italia": ["italy", "italia"],
        "Belgia": ["belgium", "belgia"],
        "Olanda": ["netherlands", "holland", "olanda"],
        "Austria": ["austria"],
        "Franta": ["france", "franta"],
        "Spania": ["spain", "espana", "spania"],
        "Romania": ["romania"]
    }

    for country, words in countries.items():
        for word in words:
            if word in text:
                return country

    return "Alta"


def pickup_to_hub_distance(p):
    return haversine(
        p.get("pickup_lat"),
        p.get("pickup_lng"),
        TIMISOARA["lat"],
        TIMISOARA["lng"]
    )


def hub_to_destination_distance(p):
    return haversine(
        TIMISOARA["lat"],
        TIMISOARA["lng"],
        p.get("destination_lat"),
        p.get("destination_lng")
    )


def safe_address(value, fallback="Necunoscut"):
    if value is None:
        return fallback
    txt = str(value).strip()
    return txt if txt else fallback


# ==================================================
# STAGE 1
# Pickup -> Timisoara Hub
# ==================================================

def build_stage_1(bookings):
    vehicles = []
    vehicle_id = 1
    remaining = bookings[:]

    while remaining:
        route = []
        occupied = 0

        first = max(remaining, key=pickup_to_hub_distance)

        route.append(first)
        occupied += seats_of(first)
        remaining.remove(first)

        while remaining:
            last = route[-1]

            nearest = min(
                remaining,
                key=lambda x: haversine(
                    last.get("pickup_lat"),
                    last.get("pickup_lng"),
                    x.get("pickup_lat"),
                    x.get("pickup_lng")
                )
            )

            if occupied + seats_of(nearest) > MAX_SEATS:
                break

            route.append(nearest)
            occupied += seats_of(nearest)
            remaining.remove(nearest)

        vehicles.append({
            "vehicle": f"RO-{vehicle_id}",
            "occupied_seats": occupied,
            "free_seats": MAX_SEATS - occupied,
            "passengers_count": len(route),
            "route": [safe_address(p.get("pickup_address")) for p in route] + ["Timisoara Hub"],
            "passengers": route
        })

        vehicle_id += 1

    return vehicles


# ==================================================
# STAGE 2
# Timisoara -> Europe Destinations
# ==================================================

def build_stage_2(bookings):
    grouped = defaultdict(list)

    for booking in bookings:
        country = detect_country(booking.get("destination_address"))
        grouped[country].append(booking)

    vehicles = []
    vehicle_id = 1

    for country, passengers in grouped.items():
        remaining = passengers[:]

        while remaining:
            route = []
            occupied = 0

            first = min(remaining, key=hub_to_destination_distance)

            route.append(first)
            occupied += seats_of(first)
            remaining.remove(first)

            while remaining:
                last = route[-1]

                nearest = min(
                    remaining,
                    key=lambda x: haversine(
                        last.get("destination_lat"),
                        last.get("destination_lng"),
                        x.get("destination_lat"),
                        x.get("destination_lng")
                    )
                )

                if occupied + seats_of(nearest) > MAX_SEATS:
                    break

                route.append(nearest)
                occupied += seats_of(nearest)
                remaining.remove(nearest)

            vehicles.append({
                "vehicle": f"EU-{vehicle_id}",
                "country": country,
                "occupied_seats": occupied,
                "free_seats": MAX_SEATS - occupied,
                "passengers_count": len(route),
                "route": ["Timisoara Hub"] + [
                    safe_address(p.get("destination_address")) for p in route
                ],
                "passengers": route
            })

            vehicle_id += 1

    return vehicles


# ==================================================
# ROUTES
# ==================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "Romania Pickup Optimizer Live"
    })


@app.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({
        "ok": True,
        "method": request.method
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "healthy": True
    })


@app.route("/optimize", methods=["POST"])
def optimize():
    try:
        payload = request.get_json(silent=True) or {}
        bookings = payload.get("bookings", [])

        if not isinstance(bookings, list):
            return jsonify({
                "success": False,
                "error": "bookings must be an array"
            }), 400

        stage1 = build_stage_1(bookings)
        stage2 = build_stage_2(bookings)

        return jsonify({
            "success": True,
            "hub": "Timisoara",
            "total_bookings": len(bookings),
            "stage_1_country_pickups": stage1,
            "stage_2_europe_routes": stage2
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500


# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)