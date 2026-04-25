from flask import Flask, request, jsonify
import os
import math
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = Flask(__name__)

# ==========================================
# CONFIG
# ==========================================
MAX_SEATS = 8
MAX_STOPS = 7
MIN_START_DISTANCE_KM = 120

TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

# ==========================================
# SAFE CONVERTERS
# ==========================================
def safe_float(val):
    try:
        if val is None or val == "":
            return None
        return float(val)
    except:
        return None


def safe_int(val, default=1):
    try:
        if val is None or val == "":
            return default
        return int(val)
    except:
        return default


# ==========================================
# DISTANCE
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ==========================================
# INPUT
# ==========================================
def normalize_input(data):
    if isinstance(data, dict) and "bookings" in data:
        return data["bookings"]

    if isinstance(data, list):
        return data

    return []


# ==========================================
# PREPARE BOOKINGS
# ==========================================
def prepare(bookings):
    cleaned = []
    skipped = []

    for b in bookings:
        pickup_lat = safe_float(b.get("pickup_lat"))
        pickup_lng = safe_float(b.get("pickup_lng"))

        if pickup_lat is None or pickup_lng is None:
            skipped.append({
                "id": b.get("id"),
                "reason": "missing pickup coordinates"
            })
            continue

        start_km = haversine(
            pickup_lat,
            pickup_lng,
            TIMISOARA["lat"],
            TIMISOARA["lng"]
        )

        if start_km < MIN_START_DISTANCE_KM:
            skipped.append({
                "id": b.get("id"),
                "reason": f"pickup under {MIN_START_DISTANCE_KM} km from Timisoara"
            })
            continue

        drop_lat = safe_float(b.get("drop_lat"))
        drop_lng = safe_float(b.get("drop_lng"))

        if drop_lat is None:
            drop_lat = TIMISOARA["lat"]

        if drop_lng is None:
            drop_lng = TIMISOARA["lng"]

        cleaned.append({
            "id": b.get("id"),
            "name": b.get("name", ""),
            "pickup_address": b.get("pickup_address", ""),
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng,
            "dropoff_address": b.get("dropoff_address", ""),
            "drop_lat": drop_lat,
            "drop_lng": drop_lng,
            "persons": safe_int(b.get("persons"), 1),
            "phone": b.get("phone", ""),
            "price": b.get("price", ""),
            "notes": b.get("notes", "")
        })

    return cleaned, skipped


# ==========================================
# MATRIX
# ==========================================
def build_matrix(bookings):
    points = [{
        "lat": TIMISOARA["lat"],
        "lng": TIMISOARA["lng"]
    }]

    for b in bookings:
        points.append({
            "lat": b["pickup_lat"],
            "lng": b["pickup_lng"]
        })

    matrix = []

    for i in range(len(points)):
        row = []

        for j in range(len(points)):
            km = haversine(
                points[i]["lat"],
                points[i]["lng"],
                points[j]["lat"],
                points[j]["lng"]
            )

            row.append(int(km * 1000))

        matrix.append(row)

    return matrix


# ==========================================
# SOLVER
# ==========================================
def solve(bookings):
    n = len(bookings)

    if n == 0:
        return []

    vehicles = max(
        1,
        math.ceil(sum(x["persons"] for x in bookings) / MAX_SEATS)
    )

    matrix = build_matrix(bookings)

    manager = pywrapcp.RoutingIndexManager(
        len(matrix),
        vehicles,
        0
    )

    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return matrix[f][t]

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Capacity
    def demand_callback(from_index):
        node = manager.IndexToNode(from_index)

        if node == 0:
            return 0

        return bookings[node - 1]["persons"]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)

    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,
        [MAX_SEATS] * vehicles,
        True,
        "Capacity"
    )

    # Max stops
    def stop_callback(from_index):
        node = manager.IndexToNode(from_index)

        if node == 0:
            return 0

        return 1

    stop_idx = routing.RegisterUnaryTransitCallback(stop_callback)

    routing.AddDimensionWithVehicleCapacity(
        stop_idx,
        0,
        [MAX_STOPS] * vehicles,
        True,
        "Stops"
    )

    search = pywrapcp.DefaultRoutingSearchParameters()

    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    search.time_limit.seconds = 10

    solution = routing.SolveWithParameters(search)

    if not solution:
        return []

    result = []

    for vehicle_id in range(vehicles):
        index = routing.Start(vehicle_id)
        route = []

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)

            if node != 0:
                route.append(bookings[node - 1])

            index = solution.Value(routing.NextVar(index))

        if route:
            result.append(route)

    return result


# ==========================================
# EXPORT
# ==========================================
def export_person(x):
    return {
        "id": x["id"],
        "name": x["name"],
        "persons": x["persons"],
        "pickup_address": x["pickup_address"],
        "pickup_lat": x["pickup_lat"],
        "pickup_lng": x["pickup_lng"],
        "dropoff_address": x["dropoff_address"],
        "drop_lat": x["drop_lat"],
        "drop_lng": x["drop_lng"],
        "phone": x["phone"],
        "price": x["price"],
        "notes": x["notes"]
    }


# ==========================================
# ROUTES
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "OR Tools Romania Optimizer"
    })


@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        if request.method == "GET":
            return jsonify({
                "status": "online",
                "message": "Use POST with bookings JSON"
            })

        raw = request.get_json(silent=True)

        bookings = normalize_input(raw)

        if not bookings:
            return jsonify({
                "status": "error",
                "message": "No bookings found"
            }), 400

        prepared, skipped = prepare(bookings)

        if not prepared:
            return jsonify({
                "status": "error",
                "message": "No valid bookings",
                "skipped": skipped
            }), 400

        routes = solve(prepared)

        cars = []

        for i, route in enumerate(routes, start=1):
            cars.append({
                "car_number": i,
                "seats_used": sum(x["persons"] for x in route),
                "total_stops": len(route),
                "route": [export_person(x) for x in route]
            })

        return jsonify({
            "status": "success",
            "total_received": len(bookings),
            "valid_bookings": len(prepared),
            "skipped_bookings": len(skipped),
            "skipped_details": skipped,
            "total_cars": len(cars),
            "cars": cars
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
