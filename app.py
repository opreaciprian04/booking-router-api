from flask import Flask, jsonify
import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

app = Flask(__name__)

MAX_SEATS = 8

TIMISOARA = {
    "name": "Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

DATABASE_URL = os.getenv("DATABASE_URL")


# ==========================================
# HELPERS
# ==========================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)

    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon/2)**2

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))


def bearing(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2-lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1))*math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1))*math.cos(math.radians(lat2))*math.cos(math.radians(lon2-lon1))

    return (math.degrees(math.atan2(y, x)) + 360) % 360


def zone_from_bearing(b):
    if b < 90:
        return "NE"
    elif b < 180:
        return "SE"
    elif b < 270:
        return "SW"
    return "NW"


# ==========================================
# DB
# ==========================================

def get_bookings_for_tomorrow():
    tomorrow = date.today() + timedelta(days=1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id,
               name,
               pickup_address,
               pickup_lat,
               pickup_lng,
               dropoff_address,
               drop_lat,
               drop_lng,
               persons
        FROM bookings
        WHERE date = %s
    """, (tomorrow,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


# ==========================================
# CORE
# ==========================================

def build_groups(rows):
    enriched = []

    for r in rows:

        if not r["pickup_lat"] or not r["pickup_lng"]:
            continue

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

        enriched.append({
            **r,
            "distance_km": round(dist, 1),
            "zone": zone_from_bearing(brg)
        })

    zones = {}

    for p in enriched:
        zones.setdefault(p["zone"], []).append(p)

    trips = []
    trip_no = 1

    for zone, people in zones.items():

        people.sort(key=lambda x: x["distance_km"], reverse=True)

        while people:

            bus = []
            seats = 0
            remain = []

            for p in people:
                needed = p.get("persons", 1)

                if seats + needed <= MAX_SEATS:
                    bus.append(p)
                    seats += needed
                else:
                    remain.append(p)

            people = remain

            trips.append({
                "trip_id": f"BUS-{trip_no:03}",
                "zone": zone,
                "count_people": seats,
                "bookings": len(bus),
                "passengers": bus
            })

            trip_no += 1

    return trips


# ==========================================
# API
# ==========================================

@app.route("/optimize")
def optimize():

    try:
        rows = get_bookings_for_tomorrow()
        trips = build_groups(rows)

        return jsonify({
    "status": "success",
    "generated_at": str(date.today()),
    "for_date": str(date.today() + timedelta(days=1)),
    "total_bookings": len(rows),
    "total_trips": len(trips),
    "trips": trips
})

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
