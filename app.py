from flask import Flask, request, jsonify
import os
import math
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# =====================================================
# FLASK APP
# =====================================================
app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
MAX_SEATS = 8

TIMISOARA = {
    "id": "TIMISOARA",
    "lat": 45.7489,
    "lng": 21.2087
}

# =====================================================
# DISTANCE HELPERS
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0

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


def distance(a, b):
    return haversine(
        float(a["lat"]),
        float(a["lng"]),
        float(b["lat"]),
        float(b["lng"])
    )


# =====================================================
# VALIDATION
# =====================================================
def normalize_bookings(bookings):
    valid = []

    for item in bookings:
        try:
            valid.append({
                "id": item.get("id"),
                "lat": float(item.get("lat")),
                "lng": float(item.get("lng"))
            })
        except:
            pass

    return valid


# =====================================================
# GROUPING LOGIC
# =====================================================
def group_into_cars(bookings):
    """
    Grupeaza simplu in masini de max 8:
    cei mai departe de Timisoara primii
    """

    for b in bookings:
        b["dist_to_tm"] = distance(b, TIMISOARA)

    bookings.sort(key=lambda x: x["dist_to_tm"], reverse=True)

    cars = []
    current = []

    for b in bookings:
        current.append(b)

        if len(current) >= MAX_SEATS:
            cars.append(current)
            current = []

    if current:
        cars.append(current)

    return cars


# =====================================================
# ORTOOLS ROUTE OPTIMIZER
# =====================================================
def optimize(passengers):
    """
    Optimizeaza pickup route catre Timisoara
    Start = primul pasager
    End = Timisoara
    """

    if len(passengers) <= 1:
        return passengers

    nodes = passengers[:] + [TIMISOARA]

    starts = [0]
    ends = [len(nodes) - 1]

    manager = pywrapcp.RoutingIndexManager(
        len(nodes),
        1,
        starts,
        ends
    )

    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)

        return int(distance(nodes[f], nodes[t]) * 1000)

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    search.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    search.time_limit.seconds = 2

    solution = routing.SolveWithParameters(search)

    if not solution:
        return passengers

    index = routing.Start(0)
    route = []

    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)

        if nodes[node_index]["id"] != "TIMISOARA":
            route.append(nodes[node_index])

        index = solution.Value(routing.NextVar(index))

    return route


# =====================================================
# MAIN PROCESS
# =====================================================
def process(bookings):
    bookings = normalize_bookings(bookings)

    if not bookings:
        return []

    cars = group_into_cars(bookings)

    result = []

    for i, car in enumerate(cars, start=1):
        optimized = optimize(car)

        result.append({
            "car_id": i,
            "seats_used": len(optimized),
            "route": optimized,
            "destination": "Timisoara"
        })

    return result


# =====================================================
# ROUTES
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Server running",
        "endpoint": "/group"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/group", methods=["GET", "POST"])
def group():

    if request.method == "GET":
        return jsonify({
            "message": "Use POST JSON",
            "example": {
                "bookings": [
                    {"id": 1, "lat": 46.77, "lng": 23.59},
                    {"id": 2, "lat": 46.17, "lng": 21.31}
                ]
            }
        })

    try:
        data = request.get_json(silent=True) or {}
        bookings = data.get("bookings", [])

        result = process(bookings)

        return jsonify({
            "success": True,
            "cars": result
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "cars": []
        }), 200


# =====================================================
# RUN
# =====================================================
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Server OK"

@app.route("/optimize", methods=["POST"])
def optimize_route():
    data = request.get_json(force=True)
    bookings = data.get("bookings", [])

    result = process(bookings)

    return jsonify({
        "success": True,
        "cars": result
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
