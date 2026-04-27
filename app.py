from flask import Flask, request, jsonify
import math
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
MAX_SEATS = 8
PORT = 5000

TIMISOARA = {
    "lat": 45.7489,
    "lng": 21.2087
}

# =====================================================
# HELPERS
# =====================================================
def to_float(v):
    try:
        return float(v)
    except:
        return 0.0

def to_int(v, default=1):
    try:
        return int(v)
    except:
        return default

def haversine(lat1, lng1, lat2, lng2):
    R = 6371.0

    lat1 = math.radians(lat1)
    lng1 = math.radians(lng1)
    lat2 = math.radians(lat2)
    lng2 = math.radians(lng2)

    dlat = lat2 - lat1
    dlng = lng2 - lng1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

# =====================================================
# ORTOOLS ROUTE
# =====================================================
def optimize_route(bookings):
    if len(bookings) <= 1:
        return bookings

    points = []
    for b in bookings:
        points.append({
            "lat": b["pickup_lat"],
            "lng": b["pickup_lng"]
        })

    size = len(points)

    matrix = []
    for i in range(size):
        row = []
        for j in range(size):
            dist = haversine(
                points[i]["lat"],
                points[i]["lng"],
                points[j]["lat"],
                points[j]["lng"]
            )
            row.append(int(dist * 1000))
        matrix.append(row)

    manager = pywrapcp.RoutingIndexManager(size, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return matrix[f][t]

    transit_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search)

    if not solution:
        return bookings

    ordered = []
    index = routing.Start(0)

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        ordered.append(bookings[node])
        index = solution.Value(routing.NextVar(index))

    return ordered

# =====================================================
# ROUTES
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "RideShare API online"
    })

@app.route("/optimize", methods=["POST"])
def optimize():
    try:
        data = request.get_json(force=True)
        raw_bookings = data.get("bookings", [])

        if not raw_bookings:
            return jsonify({
                "success": True,
                "cars_received": 0,
                "cars": []
            })

        bookings = []

        # ==========================================
        # Normalize input from JavaScript
        # ==========================================
        for r in raw_bookings:
            booking = {
                "id": r.get("id"),
                "pickup_lat": to_float(r.get("pickup_lat")),
                "pickup_lng": to_float(r.get("pickup_lng")),
                "dropoff_lat": to_float(r.get("dropoff_lat")),
                "dropoff_lng": to_float(r.get("dropoff_lng")),
                "seats": to_int(r.get("seats"), 1),
                "name": r.get("name", ""),
                "phone": r.get("phone", ""),
                "address": r.get("address", "")
            }

            booking["dist_to_tm"] = haversine(
                booking["pickup_lat"],
                booking["pickup_lng"],
                TIMISOARA["lat"],
                TIMISOARA["lng"]
            )

            bookings.append(booking)

        # ==========================================
        # Sort farthest first
        # ==========================================
        bookings.sort(key=lambda x: x["dist_to_tm"], reverse=True)

        # ==========================================
        # Build cars max 8 seats
        # ==========================================
        cars = []
        current = []
        used = 0
        car_id = 1

        for b in bookings:
            seats = b["seats"]

            if seats > MAX_SEATS:
                continue

            if used + seats <= MAX_SEATS:
                current.append(b)
                used += seats
            else:
                route = optimize_route(current)

                cars.append({
                    "car_id": car_id,
                    "seats_used": used,
                    "passengers_count": len(route),
                    "bookings": route
                })

                car_id += 1
                current = [b]
                used = seats

        if current:
            route = optimize_route(current)

            cars.append({
                "car_id": car_id,
                "seats_used": used,
                "passengers_count": len(route),
                "bookings": route
            })

        return jsonify({
            "success": True,
            "cars_received": len(cars),
            "cars": cars
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
