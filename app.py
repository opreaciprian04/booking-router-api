from flask import Flask, request, jsonify
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
import math

app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
MAX_SEATS = 8
TIMISOARA_LAT = 45.7489
TIMISOARA_LNG = 21.2087

# =====================================================
# DISTANCE
# =====================================================
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


def km(a, b):
    return haversine(a["lat"], a["lng"], b["lat"], b["lng"])


# =====================================================
# MAIN LOGIC
# =====================================================
def build_cars(bookings):
    """
    Ideea:
    - prima persoana luata = cea mai departe de Timisoara
    - restul persoanelor din masina trebuie sa fie pe traseu
    - toti ajung in acelasi timp in Timisoara
    """

    timisoara = {
        "id": 0,
        "lat": TIMISOARA_LAT,
        "lng": TIMISOARA_LNG
    }

    # calculeaza distanta la Timisoara
    for b in bookings:
        b["dist_to_tm"] = km(b, timisoara)

    # ordonare descrescator (cei mai departe primii)
    bookings.sort(key=lambda x: x["dist_to_tm"], reverse=True)

    used = set()
    cars = []

    for i, starter in enumerate(bookings):
        if starter["id"] in used:
            continue

        car = [starter]
        used.add(starter["id"])

        # prima persoana = reper
        starter_dist = starter["dist_to_tm"]

        for candidate in bookings:
            if candidate["id"] in used:
                continue

            if len(car) >= MAX_SEATS:
                break

            # conditie:
            # candidatul trebuie sa fie mai aproape de Timisoara
            if candidate["dist_to_tm"] >= starter_dist:
                continue

            # trebuie sa fie relativ aproape de traseul starter -> Timisoara
            lateral = km(starter, candidate)

            if lateral <= 60:
                car.append(candidate)
                used.add(candidate["id"])

        # ordonam masina:
        # cel mai departe -> cel mai aproape
        car.sort(key=lambda x: x["dist_to_tm"], reverse=True)

        cars.append(car)

    return cars


# =====================================================
# OPTIONAL ORTOOLS OPTIMIZATION PER CAR
# =====================================================
def optimize_route(car):
    """
    optimizeaza ordinea pickup-urilor in masina
    ultimul nod = Timisoara
    """

    nodes = car + [{
        "id": "TIMISOARA",
        "lat": TIMISOARA_LAT,
        "lng": TIMISOARA_LNG
    }]

    n = len(nodes)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0, n - 1)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)

        return int(km(nodes[f], nodes[t]) * 1000)

    transit = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search)

    if not solution:
        return car

    index = routing.Start(0)
    route = []

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route.append(nodes[node])
        index = solution.Value(routing.NextVar(index))

    route.append(nodes[manager.IndexToNode(index)])

    # scoatem Timisoara din raspuns final
    return [x for x in route if x["id"] != "TIMISOARA"]


# =====================================================
# API
# =====================================================
@app.route("/group", methods=["POST","GET"])
def group():
    data = request.get_json()

    bookings = data.get("bookings", [])

    if not bookings:
        return jsonify({"cars": []})

    cars = build_cars(bookings)

    result = []

    for idx, car in enumerate(cars, start=1):
        optimized = optimize_route(car)

        result.append({
            "car_id": idx,
            "seats_used": len(optimized),
            "route": optimized,
            "final_destination": "Timisoara"
        })

    return jsonify({"cars": result})


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
