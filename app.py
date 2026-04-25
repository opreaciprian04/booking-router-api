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
# HAVERSINE DISTANCE (km)
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
# ANGLE vs TIMISOARA
# sweep clustering
# ==========================================
def angle_from_timisoara(lat, lng):
    dy = lat - TIMISOARA["lat"]
    dx = lng - TIMISOARA["lng"]
    return math.atan2(dy, dx)


# ==========================================
# DISTANCE TO TIMISOARA
# ==========================================
def dist_to_tm(person):
    return haversine(
        person["pickup_lat"],
        person["pickup_lng"],
        TIMISOARA["lat"],
        TIMISOARA["lng"]
    )


# ==========================================
# STEP 1:
# sort geographically around Timisoara
# ==========================================
def cluster_bookings(bookings):
    enriched = []

    for b in bookings:
        item = b.copy()
        item["_angle"] = angle_from_timisoara(
            b["pickup_lat"],
            b["pickup_lng"]
        )
        item["_dist"] = dist_to_tm(b)
        enriched.append(item)

    enriched.sort(key=lambda x: (x["_angle"], -x["_dist"]))

    cars = []
    current = []

    for item in enriched:
        current.append(item)

        if len(current) == MAX_SEATS:
            cars.append(current)
            current = []

    if current:
        cars.append(current)

    return cars


# ==========================================
# STEP 2:
# inside each car sort by farthest first
# ==========================================
def optimize_route(group):
    return sorted(group, key=lambda x: x["_dist"], reverse=True)


# ==========================================
# CLEAN RESPONSE
# ==========================================
def clean_person(p):
    return {
        "id": p["id"],
        "name": p["name"],
        "pickup_lat": p["pickup_lat"],
        "pickup_lng": p["pickup_lng"]
    }


# ==========================================
# HOME
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Booking Router API V2"
    })


# ==========================================
# MAIN API
# POST /optimize
# ==========================================
@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        if request.method == "GET":
            return jsonify({
                "status": "online",
                "message": "Use POST with bookings JSON list"
            })

        data = request.get_json()

        if not data or not isinstance(data, list):
            return jsonify({
                "status": "error",
                "message": "Send JSON array"
            }), 400

        cars_raw = cluster_bookings(data)

        result = []

        for idx, group in enumerate(cars_raw, start=1):
            ordered = optimize_route(group)

            result.append({
                "car_number": idx,
                "seats_used": len(ordered),
                "destination": TIMISOARA["name"],
                "route": [clean_person(p) for p in ordered]
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
