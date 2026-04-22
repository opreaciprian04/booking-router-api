from flask import Flask, request, jsonify
import math
from collections import defaultdict

app = Flask(__name__)

# ==========================
# CONFIG
# ==========================

TIMISOARA = {
    "name": "Timisoara Hub",
    "lat": 45.7489,
    "lng": 21.2087
}

MAX_SEATS = 8

# ==========================
# HELPERS
# ==========================

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


def nearest_to_hub(passenger):
    return haversine(
        passenger["pickup_lat"],
        passenger["pickup_lng"],
        TIMISOARA["lat"],
        TIMISOARA["lng"]
    )


def country_from_address(address):
    txt = address.lower()

    if "germany" in txt or "deutschland" in txt:
        return "Germany"
    if "italy" in txt or "italia" in txt:
        return "Italy"
    if "belgium" in txt or "belgia" in txt:
        return "Belgium"
    if "netherlands" in txt or "holland" in txt:
        return "Netherlands"
    if "austria" in txt:
        return "Austria"

    return "Other"


# ==========================
# STAGE 1
# Pickup -> Timisoara
# ==========================

def build_stage1(passengers):
    # sortăm cei mai departe de hub primii
    sorted_passengers = sorted(
        passengers,
        key=nearest_to_hub,
        reverse=True
    )

    vans = []
    van_id = 1

    while sorted_passengers:
        seats_used = 0
        group = []
        remaining = []

        for p in sorted_passengers:
            seats = int(p.get("seats", 1))

            if seats_used + seats <= MAX_SEATS:
                group.append(p)
                seats_used += seats
            else:
                remaining.append(p)

        route_points = sorted(
            group,
            key=lambda x: nearest_to_hub(x),
            reverse=True
        )

        route = [x["pickup_address"] for x in route_points]
        route.append("Timisoara Hub")

        vans.append({
            "vehicle": f"RO-{van_id}",
            "used_seats": seats_used,
            "route": route,
            "passengers": group
        })

        van_id += 1
        sorted_passengers = remaining

    return vans


# ==========================
# STAGE 2
# Timisoara -> External destinations
# ==========================

def build_stage2(passengers):
    grouped_by_country = defaultdict(list)

    for p in passengers:
        country = country_from_address(
            p["destination_address"]
        )
        grouped_by_country[country].append(p)

    vans = []
    van_id = 1

    for country, plist in grouped_by_country.items():

        # sort după distanță față de Timișoara
        plist = sorted(
            plist,
            key=lambda x: haversine(
                TIMISOARA["lat"],
                TIMISOARA["lng"],
                x["destination_lat"],
                x["destination_lng"]
            )
        )

        temp = []
        seats_used = 0

        for p in plist:
            seats = int(p.get("seats", 1))

            if seats_used + seats <= MAX_SEATS:
                temp.append(p)
                seats_used += seats
            else:
                route = ["Timisoara Hub"] + [
                    x["destination_address"] for x in temp
                ]

                vans.append({
                    "vehicle": f"EU-{van_id}",
                    "country": country,
                    "used_seats": seats_used,
                    "route": route,
                    "passengers": temp
                })

                van_id += 1
                temp = [p]
                seats_used = seats

        if temp:
            route = ["Timisoara Hub"] + [
                x["destination_address"] for x in temp
            ]

            vans.append({
                "vehicle": f"EU-{van_id}",
                "country": country,
                "used_seats": seats_used,
                "route": route,
                "passengers": temp
            })

            van_id += 1

    return vans


# ==========================
# MAIN API
# ==========================

@app.route("/optimize", methods=["POST"])
def optimize():

    data = request.json

    passengers = data.get("bookings", [])

    stage1 = build_stage1(passengers)
    stage2 = build_stage2(passengers)

    return jsonify({
        "success": True,
        "hub": "Timisoara",
        "stage1_pickup_to_hub": stage1,
        "stage2_hub_to_destination": stage2
    })


@app.route("/")
def home():
    return "Romania Pickup Optimizer LIVE"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
