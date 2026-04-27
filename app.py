from flask import Flask, request, jsonify
import math
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
MAX_SEATS = 8

TIMISOARA = {
    "lat": 45.7489,
    "lng": 21.2087
}

# =====================================================
# HELPERS
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def seats_of(b):
    try:
        return int(b.get("seats", 1))
    except:
        return 1

# =====================================================
# MATRIX
# =====================================================
def build_matrix(points):
    matrix = []

    for i in range(len(points)):
        row = []
        for j in range(len(points)):
            dist = haversine(
                points[i]["lat"],
                points[i]["lng"],
                points[j]["lat"],
                points[j]["lng"]
            )
            row.append(int(dist * 1000))
        matrix.append(row)

    return matrix

# =====================================================
# ORTOOLS ROUTE INSIDE CAR
# =====================================================
def optimize_route(bookings):

    if len(bookings) <= 1:
        return bookings

    points = []

    for b in bookings:
        points.append({
            "lat": b["pickup_lat"],
            "lng": b["pickup_lng"],
            "booking": b
        })

    matrix = build_matrix(points)

    manager = pywrapcp.RoutingIndexManager(len(matrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return matrix[f][t]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(params)

    if not solution:
        return bookings

    index = routing.Start(0)
    ordered = []

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        ordered.append(points[node]["booking"])
        index = solution.Value(routing.NextVar(index))

    return ordered

# =====================================================
# ROUTES
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "ORTools RideShare API running"
    })

@app.route("/optimize", methods=["POST"])
def optimize():

    try:
        data = request.get_json(force=True)
        bookings = data.get("bookings", [])

        if not bookings:
            return jsonify({
                "success": True,
                "cars_received": 0,
                "cars": []
            })

        # sort farthest first toward Timisoara
        for b in bookings:
            b["dist_tm"] = haversine(
                b["pickup_lat"],
                b["pickup_lng"],
                TIMISOARA["lat"],
                TIMISOARA["lng"]
            )

        bookings.sort(key=lambda x: x["dist_tm"], reverse=True)

        cars = []
        current = []
        used = 0
        car_id = 1

        for b in bookings:
            s = seats_of(b)

            if s > MAX_SEATS:
                continue

            if used + s <= MAX_SEATS:
                current.append(b)
                used += s
            else:
                ordered = optimize_route(current)

                cars.append({
                    "car_id": car_id,
                    "seats_used": used,
                    "passengers_count": len(ordered),
                    "bookings": ordered
                })

                car_id += 1
                current = [b]
                used = s

        if current:
            ordered = optimize_route(current)

            cars.append({
                "car_id": car_id,
                "seats_used": used,
                "passengers_count": len(ordered),
                "bookings": ordered
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
    app.run(host="0.0.0.0", port=5000)
