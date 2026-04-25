from flask import Flask, jsonify
import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)

# ==========================================
# CONFIG
# ==========================================

TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

MAX_SEATS = 8

DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================================
# HELPERS
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


def bearing(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.cos(math.radians(lon2 - lon1))
    )

    brng = math.degrees(math.atan2(y, x))
    return (brng + 360) % 360


def zone_from_bearing(b):
    if b >= 315 or b < 45:
        return "NORD"
    elif b < 135:
        return "EST"
    elif b < 225:
        return "SUD"
    else:
        return "VEST"


# ==========================================
# DB
# ==========================================

def get_bookings_for_today():
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    today = datetime.now().date().isoformat()

    cur.execute("""
        SELECT id, name, phone, pickup_address,
               pickup_lat, pickup_lng, "date"
        FROM bookings
        WHERE "date" = %s
          AND pickup_lat IS NOT NULL
          AND pickup_lng IS NOT NULL
        ORDER BY id ASC
    """, (today,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


# ==========================================
# CORE LOGIC
# ==========================================

def build_groups(rows):
    enriched = []

    for r in rows:
        dist = haversine(
            r["pickup_lat"],
            r["pickup_lng"],
            TIMISOARA["lat"],
            TIMISOARA["lng"]
        )

        brg = bearing(
            TIMISOARA["lat"],
            TIMISOARA["lng"],
            r["pickup_lat"],
            r["pickup_lng"]
        )

        zone = zone_from_bearing(brg)

        enriched.append({
            **r,
            "distance_km": round(dist, 1),
            "zone": zone
        })

    zones = {}
    for row in enriched:
        zones.setdefault(row["zone"], []).append(row)

    trips = []
    trip_no = 1

    for zone_name, people in zones.items():

        # cel mai departe primii
        people.sort(key=lambda x: x["distance_km"], reverse=True)

        while people:
            bus = people[:MAX_SEATS]
            people = people[MAX_SEATS:]

            trips.append({
                "trip_id": f"BUS-{trip_no:03}",
                "zone": zone_name,
                "target": "Timisoara",
                "passengers": bus,
                "count": len(bus)
            })

            trip_no += 1

    return trips


# ==========================================
# ROUTE
# ==========================================

@app.route("/optimize", methods=["GET"])
def optimize():
    try:
        rows = get_bookings_for_today()
        trips = build_groups(rows)

        return jsonify({
            "status": "success",
            "date": str(datetime.now().date()),
            "target": TIMISOARA,
            "total_bookings": len(rows),
            "total_trips": len(trips),
            "trips": trips
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# CONTINUAREA ALGORITMULUI
# HUB TIMISOARA -> DESTINATII FINALE
# Adauga sub functiile existente
# ==========================================

def build_dropoff_groups(rows):
    """
    Grupeaza pasagerii care au ajuns in Timisoara
    folosind coordonatele destinatiei finale:
    drop_lat / drop_lng
    """

    enriched = []

    for r in rows:
        if r["drop_lat"] is None or r["drop_lng"] is None:
            continue

        dist = haversine(
            TIMISOARA["lat"],
            TIMISOARA["lng"],
            r["drop_lat"],
            r["drop_lng"]
        )

        brg = bearing(
            TIMISOARA["lat"],
            TIMISOARA["lng"],
            r["drop_lat"],
            r["drop_lng"]
        )

        zone = zone_from_bearing(brg)

        enriched.append({
            **r,
            "distance_km": round(dist, 1),
            "zone": zone
        })

    # grupare pe zone
    zones = {}
    for row in enriched:
        zones.setdefault(row["zone"], []).append(row)

    trips = []
    trip_no = 1

    for zone_name, people in zones.items():

        # cei mai indepartati primii
        people.sort(key=lambda x: x["distance_km"], reverse=True)

        while people:
            bus = people[:MAX_SEATS]
            people = people[MAX_SEATS:]

            # ordonare opriri:
            # de la aproape la departe sau invers
            bus_sorted = sorted(
                bus,
                key=lambda x: x["distance_km"]
            )

            trips.append({
                "trip_id": f"DROP-{trip_no:03}",
                "type": "dropoff",
                "zone": zone_name,
                "start": "Timisoara",
                "count": len(bus_sorted),
                "route": [
                    p["pickup_address"] for p in bus_sorted
                ],
                "passengers": bus_sorted
            })

            trip_no += 1

    return trips


# ==========================================
# ENDPOINT NOU
# ==========================================

@app.route("/optimize_dropoffs", methods=["GET"])
def optimize_dropoffs():
    try:
        rows = get_bookings_for_today()

        trips = build_dropoff_groups(rows)

        return jsonify({
            "status": "success",
            "mode": "Timisoara Hub -> Final Destinations",
            "date": str(datetime.now().date()),
            "target": "Timisoara",
            "total_bookings": len(rows),
            "total_trips": len(trips),
            "trips": trips
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
