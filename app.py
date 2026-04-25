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
        v = int(val)
        return max(1, v)
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
# PREPARE
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

        persons = safe_int(b.get("persons"), 1)

        # daca cineva cere >8 locuri, il limitam la 8
        if persons > MAX_SEATS:
            persons = MAX_SEATS

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
            "persons": persons,
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
# FALLBACK GROUPER (GARANTAT)
# ==========================================
def fallback_group(bookings):
    # sorteaza dupa distanta fata de Timisoara
    ordered = sorted(
        bookings,
        key=lambda x: haversine(
            x["pickup_lat"],
            x["pickup_lng"],
            TIMISOARA["lat"],
            TIMISOARA["lng"]
        ),
        reverse=True
    )

    cars = []
    current = []
    seats = 0

    for b in ordered:
        if (
            seats + b["persons"] <= MAX_SEATS
            and len(current) < MAX_STOPS
        ):
            current.append(b)
            seats += b["persons"]
        else:
            if current:
                cars.append(current)

            current = [b]
            seats = b["persons"]

    if current:
        cars.append(current)

    return cars


# ==========================================
# OR TOOLS SOLVER
# ==========================================
def solve(bookings):
    n = len(bookings)

    if n == 0:
        return []

    total_persons = sum(x["persons"] for x in bookings)

    vehicles = max(1, math.ceil(total_persons / MAX_SEATS))

    # IMPORTANT: daca ai multe bookings, da mai multe masini
    vehicles = min(vehicles + 3, n)

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

    # CAPACITY
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

    # MAX STOPS
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

    # permite vehicule nefolosite
    for v in range(vehicles):
        routing.SetFixedCostOfVehicle(0, v)

    search = pywrapcp.DefaultRoutingSearchParameters()

    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )

    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    search.time_limit.seconds = 15

    solution = routing.SolveWithParameters(search)

    if not solution:
        return fallback_group(bookings)

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

    # daca solver a returnat gol => fallback
    if not result:
        return fallback_group(bookings)

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
        "message": "Optimizer Running"
    })


@app.route("/optimize", methods=["GET", "POST"])
@app.route("/optimize", methods=["GET", "POST"])
def optimize():
    try:
        if request.method == "GET":
            return jsonify({
                "status": "online",
                "message": "Use POST with JSON"
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
                "message": "No valid bookings"
            }), 400

        routes = solve(prepared)

        valid_routes = []
        pending = []

        for route in routes:
            seats = sum(x["persons"] for x in route)

            if seats >= 3:
                valid_routes.append(route)
            else:
                pending.extend(route)

        for booking in pending:
            added = False

            for car in valid_routes:
                used = sum(x["persons"] for x in car)

                if used + booking["persons"] <= MAX_SEATS and len(car) < MAX_STOPS:
                    car.append(booking)
                    added = True
                    break

            if not added:
                valid_routes.append([booking])

        cars = []

        idx = 1
        for route in valid_routes:
            seats = sum(x["persons"] for x in route)

            if seats >= 5:
                cars.append({
                    "car_number": idx,
                    "seats_used": seats,
                    "total_stops": len(route),
                    "route": [export_person(x) for x in route]
                })
                idx += 1

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
