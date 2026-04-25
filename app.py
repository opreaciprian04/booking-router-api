from flask import Flask, jsonify, request
import math
import os

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
# DISTANCE FUNCTION
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371

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

    return dist_between + abs(dist_a_tm - dist_b_tm)


# ==========================================
# GROUPING ALGORITHM
# ==========================================
def optimize_groups(bookings):
    unassigned = bookings[:]
    trips = []

    while unassigned:
        seed = unassigned.pop(0)
        car = [seed]

        while len(car) < MAX_SEATS and unassigned:
            best = min(
                unassigned,
                key=lambda x: sum(pair_score(x, c) for c in car)
            )
            car.append(best)
            unassigned.remove(best)

        trips.append(car)

    return trips


# ==========================================
# PICKUP ORDER
# de la cel mai departe -> Timisoara
# ==========================================
def route_order(group):
    return sorted(
        group,
        key=lambda x: haversine(
            x["pickup_lat"],
            x["pickup_lng"],
            TIMISOARA["lat"],
            TIMISOARA["lng"]
        ),
        reverse=True
    )


# ==========================================
# HOME
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Optimization API running"
    })


# ==========================================
# API ROUTE
# POST /optimize
# ==========================================
@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        if request.method == "GET":
            return jsonify({
                "status": "online",
                "message": "Use POST with JSON bookings list"
            })

        data = request.get_json()

        if not data:
            return jsonify({
                "status": "error",
                "message": "No JSON received"
            }), 400

        trips = optimize_groups(data)

        result = []

        for i, trip in enumerate(trips, start=1):
            ordered = route_order(trip)

            result.append({
                "car_number": i,
                "seats_used": len(ordered),
                "route": ordered,
                "destination": TIMISOARA["name"]
            })

        return jsonify({
            "status": "success",
            "total_bookings": len(data),
            "total_cars": len(result),
            "cars": result
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
