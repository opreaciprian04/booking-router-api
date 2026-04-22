from flask import Flask, request, jsonify
import math
import os
from collections import defaultdict

aplicatie = Flask(__name__)

# ==================================================
# CONFIGURARE
# ==================================================

TIMISOARA = {
    "nume": "Hub Timisoara",
    "lat": 45.7489,
    "lng": 21.2087
}

MAX_LOCURI = 8

# ==================================================
# FUNCTII AJUTATOARE
# ==================================================

def numar(valoare, implicit=0):
    try:
        return float(valoare)
    except:
        return implicit


def distanta_haversine(lat1, lon1, lat2, lon2):
    raza = 6371

    lat1 = numar(lat1)
    lon1 = numar(lon1)
    lat2 = numar(lat2)
    lon2 = numar(lon2)

    diferenta_lat = math.radians(lat2 - lat1)
    diferenta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(diferenta_lat / 2) ** 2 +
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.sin(diferenta_lon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(raza * c, 2)


def locuri_pasager(pasager):
    try:
        locuri = int(pasager.get("locuri", pasager.get("seats", 1)))

        if locuri < 1:
            return 1

        if locuri > MAX_LOCURI:
            return MAX_LOCURI

        return locuri
    except:
        return 1


def tara_din_adresa(adresa):
    text = str(adresa).lower()

    dictionar = {
        "Germania": ["germany", "deutschland", "germania"],
        "Italia": ["italy", "italia"],
        "Belgia": ["belgium", "belgia"],
        "Olanda": ["netherlands", "holland", "olanda"],
        "Austria": ["austria"],
        "Franta": ["france", "franta"],
        "Spania": ["spain", "espana", "spania"],
        "Romania": ["romania"]
    }

    for tara, cuvinte in dictionar.items():
        for cuvant in cuvinte:
            if cuvant in text:
                return tara

    return "Alta"


def distanta_pickup_la_hub(pasager):
    return distanta_haversine(
        pasager.get("pickup_lat"),
        pasager.get("pickup_lng"),
        TIMISOARA["lat"],
        TIMISOARA["lng"]
    )


def distanta_destinatie_din_hub(pasager):
    return distanta_haversine(
        TIMISOARA["lat"],
        TIMISOARA["lng"],
        pasager.get("destination_lat"),
        pasager.get("destination_lng")
    )


# ==================================================
# ETAPA 1
# Preluare -> Timisoara
# ==================================================

def construieste_etapa1(lista_pasageri):
    masini = []
    id_masina = 1

    ramasi = lista_pasageri[:]

    while ramasi:
        masina = []
        locuri_ocupate = 0

        curent = max(ramasi, key=distanta_pickup_la_hub)

        masina.append(curent)
        locuri_ocupate += locuri_pasager(curent)
        ramasi.remove(curent)

        while ramasi:
            ultimul = masina[-1]

            urmator = min(
                ramasi,
                key=lambda x: distanta_haversine(
                    ultimul["pickup_lat"],
                    ultimul["pickup_lng"],
                    x["pickup_lat"],
                    x["pickup_lng"]
                )
            )

            if locuri_ocupate + locuri_pasager(urmator) > MAX_LOCURI:
                break

            masina.append(urmator)
            locuri_ocupate += locuri_pasager(urmator)
            ramasi.remove(urmator)

        traseu = [p["pickup_address"] for p in masina]
        traseu.append("Hub Timisoara")

        masini.append({
            "vehicul": f"RO-{id_masina}",
            "traseu": traseu,
            "pasageri": masina,
            "locuri_ocupate": locuri_ocupate,
            "locuri_libere": MAX_LOCURI - locuri_ocupate,
            "numar_pasageri": len(masina)
        })

        id_masina += 1

    return masini


# ==================================================
# ETAPA 2
# Timisoara -> Destinatii
# ==================================================

def construieste_etapa2(lista_pasageri):
    masini = []
    id_masina = 1

    grupate = defaultdict(list)

    for pasager in lista_pasageri:
        grupate[tara_din_adresa(pasager["destination_address"])].append(pasager)

    for tara, pasageri in grupate.items():

        ramasi = pasageri[:]

        while ramasi:
            masina = []
            locuri_ocupate = 0

            curent = min(
                ramasi,
                key=lambda x: distanta_destinatie_din_hub(x)
            )

            masina.append(curent)
            locuri_ocupate += locuri_pasager(curent)
            ramasi.remove(curent)

            while ramasi:
                ultimul = masina[-1]

                urmator = min(
                    ramasi,
                    key=lambda x: distanta_haversine(
                        ultimul["destination_lat"],
                        ultimul["destination_lng"],
                        x["destination_lat"],
                        x["destination_lng"]
                    )
                )

                if locuri_ocupate + locuri_pasager(urmator) > MAX_LOCURI:
                    break

                masina.append(urmator)
                locuri_ocupate += locuri_pasager(urmator)
                ramasi.remove(urmator)

            traseu = ["Hub Timisoara"] + [
                p["destination_address"] for p in masina
            ]

            masini.append({
                "vehicul": f"EU-{id_masina}",
                "tara": tara,
                "traseu": traseu,
                "pasageri": masina,
                "locuri_ocupate": locuri_ocupate,
                "locuri_libere": MAX_LOCURI - locuri_ocupate,
                "numar_pasageri": len(masina)
            })

            id_masina += 1

    return masini


# ==================================================
# RUTE API
# ==================================================

@aplicatie.route("/", methods=["GET"])
def acasa():
    return jsonify({
        "status": "online",
        "serviciu": "Optimizator Romania Pickup V2"
    })


@aplicatie.route("/ping", methods=["GET", "POST"])
def ping():
    return jsonify({
        "ok": True,
        "metoda": request.method,
        "mesaj": "API functioneaza"
    })


@aplicatie.route("/optimize", methods=["POST"])
def optimizeaza():
    try:
        date = request.get_json(force=True, silent=True) or {}

        rezervari = date.get("bookings", [])

        if not isinstance(rezervari, list):
            return jsonify({
                "success": False,
                "eroare": "bookings trebuie sa fie lista"
            }), 400

        etapa1 = construieste_etapa1(rezervari)
        etapa2 = construieste_etapa2(rezervari)

        return jsonify({
            "success": True,
            "hub": "Timisoara",
            "total_rezervari": len(rezervari),
            "etapa1_preluare_la_hub": etapa1,
            "etapa2_hub_la_destinatie": etapa2
        })

    except Exception as eroare:
        return jsonify({
            "success": False,
            "eroare": str(eroare)
        }), 500


# ==================================================
# PORNIRE
# ==================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    aplicatie.run(host="0.0.0.0", port=port)
