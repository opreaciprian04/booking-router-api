from flask import Flask, request, jsonify
import os
import math
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

app = Flask(__name__)

# ==================================================
# CONFIG
# ==================================================
MAX_SEATS = 8
TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

# ==================================================
# HELPERS
# ==================================================
def safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except:
        return None


def safe_int(v, default=1):
    try:
        if v is None or v == "":
            return default
        return max(1, int(v))
    except:
        return default


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


def normalize_input(data):
    if isinstance(data, dict) and "bookings" in data:
        return data["bookings"]
    if isinstance(data, list):
        return data
    return []


# ==================================================
# PREPARE BOOKINGS
# ==================================================
def prepare(bookings):
    cleaned = []
    skipped = []

    for b in bookings:
        pickup_lat = safe_float(b.get("pickup_lat"))
        pickup_lng = safe_float(b.get("pickup_lng"))
        drop_lat = safe_float(b.get("drop_lat"))
        drop_lng = safe_float(b.get("drop_lng"))

        if pickup_lat is None or pickup_lng is None:
            skipped.append({
                "id": b.get("id"),
                "reason": "missing pickup coords"
            })
            continue

        if drop_lat is None or drop_lng is None:
            skipped.append({
                "id": b.get("id"),
                "reason": "missing dropoff coords"
            })
            continue

        persons = safe_int(b.get("persons"), 1)
        if persons > MAX_SEATS:
            persons = MAX_SEATS

        cleaned.append({
            "id": b.get("id"),
            "name": b.get("name", ""),
            "persons": persons,
            "pickup_address": b.get("pickup_address", ""),
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng,
            "dropoff_address": b.get("dropoff_address", ""),
            "drop_lat": drop_lat,
            "drop_lng": drop_lng,
            "phone": b.get("phone", ""),
            "price": b.get("price", ""),
            "notes": b.get("notes", "")
        })

    return cleaned, skipped


# ==================================================
# GENERIC ORTOOLS SOLVER
# ==================================================
def solve_routes(bookings, start_mode="pickup"):
    """
    start_mode:
    pickup  = optimize pickup -> Timisoara
    dropoff = optimize Timisoara -> dropoff
    """

    if not bookings:
        return []

    total_persons = sum(x["persons"] for x in bookings)
    vehicles = max(1, math.ceil(total_persons / MAX_SEATS))

    # Nodes
    points = [{
        "lat": TIMISOARA["lat"],
        "lng": TIMISOARA["lng"]
    }]

    for b in bookings:
        if start_mode == "pickup":
            points.append({
                "lat": b["pickup_lat"],
                "lng": b["pickup_lng"]
            })
        else:
            points.append({
                "lat": b["drop_lat"],
                "lng": b["drop_lng"]
            })

    # Matrix
    matrix = []
    for i in range(len(points)):
        row = []
        for j in range(len(points)):
            km = haversine(
                points[i]["lat"], points[i]["lng"],
                points[j]["lat"], points[j]["lng"]
            )
            row.append(int(km * 1000))
        matrix.append(row)

    manager = pywrapcp.RoutingIndexManager(len(matrix), vehicles, 0)
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


# ==================================================
# EXPORT
# ==================================================
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


def export_routes(routes):
    cars = []

    for i, route in enumerate(routes, start=1):
        cars.append({
            "car_number": i,
            "seats_used": sum(x["persons"] for x in route),
            "total_stops": len(route),
            "route": [export_person(x) for x in route]
        })

    return cars


# ==================================================
# ROUTES
# ==================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "2 Step OR-Tools Optimizer"
    })


@app.route("/optimize", methods=["POST"])
def optimize():
    try:
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
                "message": "No valid bookings"
            }), 400

        # STEP 1 = Pickup -> Timisoara
        pickup_routes = solve_routes(prepared, "pickup")

        # STEP 2 = Timisoara -> Dropoff
        dropoff_routes = solve_routes(prepared, "dropoff")

        return jsonify({
            "status": "success",
            "total_received": len(bookings),
            "valid_bookings": len(prepared),
            "skipped_bookings": len(skipped),
            "skipped_details": skipped,

            "phase_1_pickup_to_timisoara": {
                "total_cars": len(pickup_routes),
                "cars": export_routes(pickup_routes)
            },

            "phase_2_timisoara_to_dropoff": {
                "total_cars": len(dropoff_routes),
                "cars": export_routes(dropoff_routes)
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ==================================================
# RUN
# ==================================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
