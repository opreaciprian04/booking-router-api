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
TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

# ==========================================
# DISTANCE
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)

    a = (
        math.sin(dLat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(dLon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ==========================================
# BUILD MATRIX
# node 0 = Timisoara depot
# nodes 1..n = passengers
# ==========================================
def create_distance_matrix(bookings):
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
            d = haversine(
                points[i]["lat"], points[i]["lng"],
                points[j]["lat"], points[j]["lng"]
            )
            row.append(int(d * 1000))
        matrix.append(row)

    return matrix


# ==========================================
# SOLVER
# ==========================================
def solve_routes(bookings):
    n = len(bookings)
    vehicles = math.ceil(n / MAX_SEATS)

    distance_matrix = create_distance_matrix(bookings)

    manager = pywrapcp.RoutingIndexManager(
        len(distance_matrix),
        vehicles,
        0
    )

    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return distance_matrix[f][t]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Capacity
    def demand_callback(from_index):
        node = manager.IndexToNode(from_index)
        return 0 if node == 0 else 1

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [MAX_SEATS] * vehicles,
        True,
        "Capacity"
    )

    # Search params
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search_parameters)

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
# API
# ==========================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Romania Transport Optimizer PRO"
    })


@app.route("/optimize", methods=["POST", "GET"])
def optimize():
    try:
        if request.method == "GET":
            return jsonify({
                "status": "online",
                "message": "Use POST JSON list"
            })

        data = request.get_json()

        if not isinstance(data, list):
            return jsonify({
                "error": "Send JSON array"
            }), 400

        routes = solve_routes(data)

        cars = []

        for i, route in enumerate(routes, start=1):
            cars.append({
                "car_number": i,
                "seats_used": len(route),
                "destination": "Timisoara",
                "route": route
            })

        return jsonify({
            "status": "success",
            "total_bookings": len(data),
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
