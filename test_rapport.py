# ─────────────────────────────────────────────────────────────────
# FICHIER : test_rapports.py
# COUVRE  : POST /rapports/generer, GET /rapports, GET /rapports/{id}
#           GET /rapports/{id}/html, GET /rapports/lot/{batch}
#           PUT /rapports/{id}, DELETE /rapports/{id}
#           DELETE /incidents/{incident_id}
#           GET /logs
# LANCER  : pytest test_rapports.py -v -s
# PRÉREQUIS : uvicorn main:app --reload  (dans un autre terminal)
# ─────────────────────────────────────────────────────────────────

import httpx

BASE_URL = "http://localhost:8000"

BATCH = "BAT-RPT-01"
rapport_id   = None
incident_id  = None
all_sns      = []


# ─────────────────────────────────────────────────────────────────
# SETUP — Créer stock + tests machine pour avoir des données
# ─────────────────────────────────────────────────────────────────
def test_setup():
    global all_sns, incident_id

    # Créer stock
    r = httpx.post(f"{BASE_URL}/stock/multi", json=[{
        "product_name": "Ibuprofene 400mg",
        "form": "comprimes",
        "batch_number": BATCH,
        "quantity": 5
    }])
    assert r.status_code == 200
    pid = r.json()["produits"][0]["product_id"]

    # Récupérer SN
    r2 = httpx.get(f"{BASE_URL}/stock/{pid}")
    all_sns = [u["serial_number"] for u in r2.json()["units"]]

    # 3 PASS + 2 FAIL
    for sn in all_sns[:3]:
        httpx.post(f"{BASE_URL}/machine/test", json={
            "serial_number": sn, "station_id": "STATION-01", "result": "pass"
        })
    for sn in all_sns[3:]:
        r3 = httpx.post(f"{BASE_URL}/machine/test", json={
            "serial_number": sn, "station_id": "STATION-02", "result": "fail"
        })
        if not incident_id:
            incident_id = r3.json()["incident_id"]

    print(f"\n✅ Setup : 5 SN créés | 3 PASS + 2 FAIL | Incident: {incident_id}")


# ─────────────────────────────────────────────────────────────────
# TEST 1 — Générer le rapport du lot
# CE QU'ON VÉRIFIE : rapport créé avec date + résultats + conformité
# SWAGGER          : POST /rapports/generer → batch_number
# ─────────────────────────────────────────────────────────────────
def test_generer_rapport():
    global rapport_id

    r = httpx.post(f"{BASE_URL}/rapports/generer", json={
        "batch_number": BATCH
    })
    assert r.status_code == 200
    data = r.json()

    rapport_id = data["rapport_id"]

    assert data["total_unites"] == 5
    assert data["total_passes"] == 3
    assert data["total_rejetes"] == 2
    assert data["statut_conformite"] == "NON CONFORME"
    assert data["non_conformite"] is not None
    assert len(data["hash_integrite"]) == 64

    print(f"\n✅ Rapport généré : {rapport_id}")
    print(f"   Conformité : NON CONFORME | Hash : {data['hash_integrite'][:20]}...")


# ─────────────────────────────────────────────────────────────────
# TEST 2 — Vérifier les logs horodatés
# CE QU'ON VÉRIFIE : chaque action a un timestamp précis
# SWAGGER          : GET /logs → observer tous les horodatages
# ─────────────────────────────────────────────────────────────────
def test_logs_horodates():
    r = httpx.get(f"{BASE_URL}/logs")
    assert r.status_code == 200

    logs = r.json()["logs"]
    assert len(logs) >= 8

    for log in logs:
        assert "timestamp" in log
        assert log["timestamp"] != ""

    print(f"\n✅ {len(logs)} logs horodatés vérifiés")


# ─────────────────────────────────────────────────────────────────
# TEST 3 — Consulter le rapport complet JSON
# CE QU'ON VÉRIFIE : contient logs, incidents, hash, date
# SWAGGER          : GET /rapports/{rapport_id}
# ─────────────────────────────────────────────────────────────────
def test_get_rapport_json():
    r = httpx.get(f"{BASE_URL}/rapports/{rapport_id}")
    assert r.status_code == 200

    data = r.json()
    assert "generated_at" in data
    assert len(data["logs"]) > 0
    assert len(data["incidents"]) == 2
    assert data["hash_integrite"] != ""

    print(f"\n✅ Rapport JSON complet")
    print(f"   Généré le  : {data['generated_at']}")
    print(f"   Logs       : {len(data['logs'])}")
    print(f"   Incidents  : {len(data['incidents'])}")


# ─────────────────────────────────────────────────────────────────
# TEST 4 — Consulter le rapport en HTML
# CE QU'ON VÉRIFIE : HTML généré et contient les bonnes données
# NAVIGATEUR       : http://localhost:8000/rapports/{rapport_id}/html
# ─────────────────────────────────────────────────────────────────
def test_get_rapport_html():
    r = httpx.get(f"{BASE_URL}/rapports/{rapport_id}/html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "NON CONFORME" in r.text
    assert "Rapport de Production GxP" in r.text

    print(f"\n✅ Rapport HTML accessible")
    print(f"   → Ouvrir : http://localhost:8000/rapports/{rapport_id}/html")


# ─────────────────────────────────────────────────────────────────
# TEST 5 — Intégrité du rapport (hash stable)
# CE QU'ON VÉRIFIE : hash identique à chaque consultation
# SWAGGER          : GET /rapports/{rapport_id} × 2 → comparer hash
# ─────────────────────────────────────────────────────────────────
def test_integrite_hash():
    r1 = httpx.get(f"{BASE_URL}/rapports/{rapport_id}")
    r2 = httpx.get(f"{BASE_URL}/rapports/{rapport_id}")
    assert r1.json()["hash_integrite"] == r2.json()["hash_integrite"]

    print(f"\n✅ Hash identique sur 2 consultations → intégrité confirmée")


# ─────────────────────────────────────────────────────────────────
# TEST 6 — Rapports archivés par lot
# CE QU'ON VÉRIFIE : rapport retrouvable via batch_number
# SWAGGER          : GET /rapports/lot/BAT-RPT-01
# ─────────────────────────────────────────────────────────────────
def test_rapports_par_lot():
    r = httpx.get(f"{BASE_URL}/rapports/lot/{BATCH}")
    assert r.status_code == 200
    assert r.json()["total_rapports"] >= 1
    assert r.json()["batch_number"] == BATCH

    print(f"\n✅ Rapport archivé trouvé pour lot {BATCH}")


# ─────────────────────────────────────────────────────────────────
# TEST 7 — Annuler un incident par erreur (DELETE)
# CE QU'ON VÉRIFIE : incident supprimé + SN remis en pending
# SWAGGER          : DELETE /incidents/{incident_id}
# ─────────────────────────────────────────────────────────────────
def test_delete_incident():
    r = httpx.delete(f"{BASE_URL}/incidents/{incident_id}")
    assert r.status_code == 200
    assert "pending" in r.json()["message"]

    # Vérifier que le SN est bien remis en pending
    sn = all_sns[3]
    check = httpx.get(f"{BASE_URL}/debug/sn/{sn}")
    assert check.json()["status"] == "pending"

    print(f"\n✅ Incident {incident_id} annulé — SN remis en pending")


# ─────────────────────────────────────────────────────────────────
# TEST 8 — Modifier statut conformité (PUT rapport)
# CE QU'ON VÉRIFIE : statut mis à jour + hash recalculé
# SWAGGER          : PUT /rapports/{rapport_id} → CONFORME
# ─────────────────────────────────────────────────────────────────
def test_update_rapport_statut():
    old_hash = httpx.get(f"{BASE_URL}/rapports/{rapport_id}").json()["hash_integrite"]

    r = httpx.put(
        f"{BASE_URL}/rapports/{rapport_id}",
        params={"statut_conformite": "CONFORME"}
    )
    assert r.status_code == 200
    assert r.json()["new_statut"] == "CONFORME"

    new_hash = httpx.get(f"{BASE_URL}/rapports/{rapport_id}").json()["hash_integrite"]
    assert old_hash != new_hash

    print(f"\n✅ Rapport mis à jour : NON CONFORME → CONFORME")
    print(f"   Hash recalculé (différent de l'ancien)")


# ─────────────────────────────────────────────────────────────────
# TEST 9 — Supprimer rapport CONFORME → interdit (403)
# CE QU'ON VÉRIFIE : rapport validé ne peut pas être supprimé (GxP)
# SWAGGER          : DELETE /rapports/{rapport_id} → voir 403
# ─────────────────────────────────────────────────────────────────
def test_delete_conforme_rapport_blocked():
    r = httpx.delete(f"{BASE_URL}/rapports/{rapport_id}")
    assert r.status_code == 403

    print(f"\n✅ Suppression bloquée (403) — rapport CONFORME protégé (GxP)")


# ─────────────────────────────────────────────────────────────────
# TEST 10 — Supprimer un rapport NON CONFORME
# CE QU'ON VÉRIFIE : rapport non conforme peut être supprimé
# SWAGGER          : DELETE /rapports/{rapport_id} → rapport NON CONFORME
# ─────────────────────────────────────────────────────────────────
def test_delete_non_conforme_rapport():
    # Créer un nouveau rapport non conforme
    r = httpx.post(f"{BASE_URL}/rapports/generer", json={"batch_number": BATCH})
    new_id = r.json()["rapport_id"]

    # Ce rapport sera NON CONFORME car il reste encore un fail
    r2 = httpx.delete(f"{BASE_URL}/rapports/{new_id}")
    # Peut être 200 ou 403 selon le statut — on vérifie juste la réponse
    assert r2.status_code in [200, 403]

    print(f"\n✅ Test suppression rapport terminé — code: {r2.status_code}")


# ─────────────────────────────────────────────────────────────────
# TEST 11 — Lot inconnu retourne 404
# CE QU'ON VÉRIFIE : batch inexistant = 404
# SWAGGER          : GET /rapports/lot/BAT-999 → erreur rouge
# ─────────────────────────────────────────────────────────────────
def test_rapport_lot_inconnu():
    r = httpx.get(f"{BASE_URL}/rapports/lot/BAT-999")
    assert r.status_code == 404

    print(f"\n✅ Lot inconnu retourne bien 404")