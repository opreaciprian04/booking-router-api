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
# SMART CLUSTERING MAX EFFICIENCY
# =====================================================
def group_into_cars(bookings):
    """
    Grupare inteligenta:
    1. cei mai departe de Timisoara primii
    2. umple masina cu cei apropiati geografic
    3. maximizeaza ocuparea locurilor
    """

    if not bookings:
        return []

    for b in bookings:
        b["dist_to_tm"] = distance(b, TIMISOARA)

    # cei mai departe primii
    unassigned = sorted(bookings, key=lambda x: x["dist_to_tm"], reverse=True)

    cars = []

    while unassigned:
        seed = unassigned.pop(0)
        car = [seed]

        while len(car) < MAX_SEATS and unassigned:

            best_idx = None
            best_score = 999999

            for idx, candidate in enumerate(unassigned):

                # distanta fata de ultimul pasager din masina
                near_last = distance(candidate, car[-1])

                # directie spre Timisoara similara
                delta_tm = abs(candidate["dist_to_tm"] - seed["dist_to_tm"])

                score
