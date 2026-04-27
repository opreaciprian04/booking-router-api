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
    "lng": 21.2087,
    "name": "Timisoara"
}

# =====================================================
# HELPERS
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dlon / 2) ** 2
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
# NORMALIZE INPUT
# =====================================================
def normalize_bookings(bookings):
    valid = []

    for item in bookings:
        try:
            lat = float(item.get("pickup_lat", item.get("lat")))
            lng = float(item.get("pickup_lng", item.get("lng")))

            valid.append({
                **item,
                "id": item.get("id"),
                "lat": lat,
                "lng": lng,
                "persons": int(item.get("persons", 1))
            })

        except:
            pass

    return valid


# =====================================================
# GROUP BOOKINGS INTO CARS
# =====================================================
def group_into_cars(bookings):
    """
    Grupeaza oamenii apropiati geografic.
    Primul = cel mai departe de Timisoara
    """
    for b in bookings:
        b["dist_to_tm"] = distance(b, TIMISOARA)

    # cei mai departe primii
    remaining = sorted(bookings, key=lambda x: x["dist_to_tm"], reverse=True)

    cars = []

    while remaining:
        seed = remaining.pop(0)

        current_car = [seed]
        used_seats = seed["persons"]

        # sortam restul dupa apropiere de seed
        remaining.sort(key=lambda x: distance(seed, x))

        selected = []

        for item in remaining:
            if used_seats + item["persons"] <= MAX_SEATS:
                current_car.append(item)
                used_seats += item["persons"]
                selected.append(item)

        for s in selected:
            remaining.remove(s)

        cars.append(current_car)

    return cars


# =====================================================
# ORTOOLS ROUTE OPTIMIZER
# =====================================================
def optimize_route(passengers):
    """
    Optimizeaza ordinea pickup-urilor pana la Timisoara
    """
    if len(passengers) <= 1:
        return passengers

    nodes = passengers[:] + [TIMISOARA]

    manager = pywrapcp.RoutingIndexManager(
        len(nodes),
        1,
        [0],
        [len(nodes) - 1]
    )

    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)

        return int(distance(nodes[f], nodes[t]) * 1000)

    transit_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    params = pywrapcp.DefaultRoutingSearchParameters()

    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )

    params.time_limit.seconds = 2

    solution = routing.SolveWithParameters(params)

    if not solution:
        return passengers

    route = []
    index = routing.Start(0)

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)

        if nodes[node]["id"] != "TIMISOARA":
            route.append(nodes[node])

        index = solution.Value(routing.NextVar(index))

    return route


# =====================================================
# PROCESS
# =====================================================
def process(bookings):
    bookings = normalize_bookings(bookings)

    if not bookings:
        return []

    grouped = group_into_cars(bookings)

    result = []

    for i, car in enumerate(grouped, start=1):
        optimized = optimize_route(car)

        seats_used = sum(x["persons"] for x in optimized)

        result.append({
            "car_id": i,
            "destination": "Timisoara",
            "seats_used": seats_used,
            "stops": len(optimized),
            "route": optimized
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
        "endpoints": [
            "/health",
            "/group",
            "/optimize"
        ]
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
                    {
                        "id": 1,
                        "pickup_lat": 46.77,
                        "pickup_lng": 23.59,
                        "persons": 2
                    }
                ]
            }
        })

    try:
        data = request.get_json(force=True)
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


@app.route("/optimize", methods=["POST"])
def optimize_endpoint():
    try:
        data = request.get_json(force=True)

        # caz 1: {"bookings":[...]}
        if isinstance(data, dict):
            bookings = data.get("bookings", [])

        # caz 2: direct listă [...]
        elif isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict) and "bookings" in data[0]:
                bookings = data[0]["bookings"]
            else:
                bookings = data

        else:
            bookings = []

        result = process(bookings)

        return jsonify({
            "success": True,
            "received": len(bookings),
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
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
