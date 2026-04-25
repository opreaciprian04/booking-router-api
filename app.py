from flask import Flask, jsonify, request
import math

app = Flask(__name__)

# ==========================================
# CONFIG
# ==========================================
MAX_SEATS = 8

TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

# ==========================================
# SAMPLE INPUT
# Primește JSON listă rezervări
# fiecare rezervare trebuie să aibă:
# id, name, pickup_lat, pickup_lng
# ==========================================

# ==========================================
# DISTANCE FUNCTION
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km

    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)

    a = (
        math.sin(dLat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dLon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ==========================================
# SCORE: apropiere între oameni + direcție spre Timișoara
# ==========================================
def pair_score(a, b):
    dist_between = haversine(
        a["pickup_lat"], a["pickup_lng"],
        b["pickup_lat"], b["pickup_lng"]
    )

    dist_a_tm = haversine(
        a["pickup_lat"], a["pickup_lng"],
        TIMISOARA["lat"], TIMISOARA["lng"]
    )

    dist_b_tm = haversine(
        b["pickup_lat"], b["pickup_lng"],
        TIMISOARA["lat"], TIMISOARA["lng"]
    )

    # vrem apropiere între pasageri
    # și distanță similară până la Timișoara
    return dist_between + abs(dist_a_tm - dist_b_tm)


# ==========================================
# GROUPING
# ==========================================
def optimize_groups(bookings):
    unassigned = bookings[:]
    trips = []

    while unassigned:
        seed = unassigned.pop(0)
        car = [seed]

        while len(car) < MAX_SEATS and unassigned:
            best = min(unassigned, key=lambda x: sum(pair_score(x, c) for c in car))
            car.append(best)
            unassigned.remove(best)

        trips.append(car)

    return trips


# ==========================================
# SORT PICKUP ORDER
# De la cel mai departe -> spre Timișoara
# ==========================================
def route_order(group):
    return sorted(
        group,
        key=lambda x: haversine(
            x["pickup_lat"], x["pickup_lng"],
            TIMISOARA["lat"], TIMISOARA["lng"]
        ),
        reverse=True
    )


# ==========================================
# API ROUTE
# POST /optimize
# ==========================================
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        data = request.get_json(force=True, silent=True)

        return jsonify({
            "status": "ok",
            "method": request.method,
            "received": data
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

app.run(host="0.0.0.0", port=5000)
