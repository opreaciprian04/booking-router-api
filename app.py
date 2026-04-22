from flask import Flask, request, jsonify
from collections import defaultdict
import math

app = Flask(__name__)

# HUB CENTRAL
HUB = {
    "city": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

CAPACITY = 8


def distance(a, b):
    return math.sqrt(
        (a["lat"] - b["lat"]) ** 2 +
        (a["lng"] - b["lng"]) ** 2
    )


@app.route("/", methods=["GET"])
def home():
    return "Romania Pickup Optimizer Live"


@app.route("/optimize-romania", methods=["POST"])
def optimize_romania():
    data = request.get_json()
    bookings = data.get("bookings", [])

    if not bookings:
        return jsonify({"error": "No bookings"}), 400

    # sortare după distanța față de Timișoara
    bookings_sorted = sorted(
        bookings,
        key=lambda x: distance(x, HUB)
    )

    vehicles = []
    current_vehicle = []
    vehicle_id = 1

    for booking in bookings_sorted:
        current_vehicle.append(booking)

        if len(current_vehicle) == CAPACITY:
            vehicles.append({
                "vehicle": vehicle_id,
                "route_to": "Timisoara",
                "passengers": current_vehicle
            })
            vehicle_id += 1
            current_vehicle = []

    if current_vehicle:
        vehicles.append({
            "vehicle": vehicle_id,
            "route_to": "Timisoara",
            "passengers": current_vehicle
        })

    return jsonify({
        "success": True,
        "hub": "Timisoara",
        "vehicles": vehicles
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
