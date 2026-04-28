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
        if v is None or v == "":
            return 0.0
        return float(v)
    except:
        return 0.0

def to_int(v, default=1):
    try:
        if v is None or v == "":
            return default
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

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

# =====================================================
# GET FIRST EXISTING FIELD
# =====================================================
def pick(obj, keys, default=None):
    for k in keys:
        if k in obj and obj[k] not in [None, ""]:
            return obj[k]
    return default

# =====================================================
# ORTOOLS
# =====================================================
def optimize_route(bookings):
    if len(bookings) <= 1:
        return bookings

    size = len(bookings)

    matrix = []
    for i in range(size):
        row = []
        for j in range(size):
            dist = haversine(
                bookings[i]["pickup_lat"],
                bookings[i]["pickup_lng"],
                bookings[j]["pickup_lat"],
                bookings[j]["pickup_lng"]
            )
            row.append(int(dist * 1000))
        matrix.append(row)

    manager = pywrapcp.RoutingIndexManager(size, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return matrix[f][t]

    transit = routing.RegisterTransitCallback(callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(params)

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
# HOME
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "API online"
    })

# =====================================================
# MAIN
# =====================================================
@app.route("/optimize", methods=["POST"])
def optimize():

    try:
        data = request.get_json(force=True)

        # ==========================================
        # ACCEPT ALL POSSIBLE N8N FORMATS
        # ==========================================
        raw_bookings = []

        if isinstance(data, list):
            raw_bookings = data

        elif isinstance(data, dict):

            if "bookings" in data:
                raw_bookings = data["bookings"]

            elif "data" in data:
                raw_bookings = data["data"]

            elif "items" in data:
                raw_bookings = data["items"]

            else:
                # single booking object
                raw_bookings = [data]

        if not raw_bookings:
            return jsonify({
                "success": True,
                "cars_received": 0,
                "received_payload": data,
                "cars": []
            })

        bookings = []

        # ==========================================
        # NORMALIZE BOOKINGS
        # ==========================================
        for r in raw_bookings:

            pickup_lat = to_float(pick(r, [
                "pickup_lat", "lat", "pickupLat"
            ]))

            pickup_lng = to_float(pick(r, [
                "pickup_lng", "lng", "pickupLng"
            ]))

            dropoff_lat = to_float(pick(r, [
                "dropoff_lat", "dest_lat"
            ]))

            dropoff_lng = to_float(pick(r, [
                "dropoff_lng", "dest_lng"
            ]))

            seats = to_int(pick(r, [
                "seats", "persons", "passengers"
            ]), 1)

            if pickup_lat == 0 or pickup_lng == 0:
                continue

            booking = {
                "id": pick(r, ["id"], ""),
                "name": pick(r, ["name"], ""),
                "phone": pick(r, ["phone"], ""),
                "address": pick(r, ["address", "pickup_address"], ""),
                "pickup_lat": pickup_lat,
                "pickup_lng": pickup_lng,
                "dropoff_address": pick(r,["dropoff_address"], ""),
                "dropoff_lat": dropoff_lat,
                "dropoff_lng": dropoff_lng,
                "seats": seats,
                "price": pick(r,["price"], ""),
            
            }

            booking["dist_to_tm"] = haversine(
                pickup_lat,
                pickup_lng,
                TIMISOARA["lat"],
                TIMISOARA["lng"]
            )

            bookings.append(booking)

        if not bookings:
            return jsonify({
                "success": True,
                "cars_received": 0,
                "reason": "No valid coordinates",
                "cars": []
            })

        # ==========================================
        # SORT FAR FIRST
        # ==========================================
        bookings.sort(key=lambda x: x["dist_to_tm"], reverse=True)

        # ==========================================
        # BUILD CARS
        # ==========================================
        cars = []
        current = []
        used = 0
        car_id = 1

        for b in bookings:

            if b["seats"] > MAX_SEATS:
                continue

            if used + b["seats"] <= MAX_SEATS:
                current.append(b)
                used += b["seats"]

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
                used = b["seats"]

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
            "valid_bookings": len(bookings),
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
