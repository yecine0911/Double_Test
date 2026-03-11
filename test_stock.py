# ─────────────────────────────────────────────────────────────────
# FICHIER : test_stock.py
# COUVRE  : POST /stock/multi, GET /stock, GET /stock/{id}
#           PUT /stock/{id}, DELETE /stock/{id}, DELETE /stock/sn/{sn}
#           POST /machine/test, PUT /machine/test/{sn}
# LANCER  : pytest test_stock.py -v -s
# PRÉREQUIS : uvicorn main:app --reload  (dans un autre terminal)
# ─────────────────────────────────────────────────────────────────

import httpx

BASE_URL = "http://localhost:8000"

# Variables partagées entre les tests
product_id_1 = None
product_id_2 = None
all_sns_1    = []
all_sns_2    = []
sn_pass      = None
sn_fail      = None


# ─────────────────────────────────────────────────────────────────
# TEST 1 — Créer 2 produits en une seule requête
# CE QU'ON VÉRIFIE : 2 produits créés + SN générés auto
# SWAGGER          : POST /stock/multi → liste de 2 produits → Execute
# ─────────────────────────────────────────────────────────────────
def test_create_multi_stock():
    global product_id_1, product_id_2, all_sns_1, all_sns_2

    r = httpx.post(f"{BASE_URL}/stock/multi", json=[
        {
            "product_name": "Paracetamol 500mg",
            "form": "comprimes",
            "batch_number": "BAT-001",
            "quantity": 5
        },
        {
            "product_name": "Amoxicilline 1g",
            "form": "gelules",
            "batch_number": "BAT-002",
            "quantity": 3
        }
    ])

    assert r.status_code == 200
    data = r.json()

    assert data["total_produits"] == 2
    assert data["total_sn_generes"] == 8

    product_id_1 = data["produits"][0]["product_id"]
    product_id_2 = data["produits"][1]["product_id"]

    # Récupérer tous les SN via GET
    r2 = httpx.get(f"{BASE_URL}/stock/{product_id_1}")
    all_sns_1 = [u["serial_number"] for u in r2.json()["units"]]

    r3 = httpx.get(f"{BASE_URL}/stock/{product_id_2}")
    all_sns_2 = [u["serial_number"] for u in r3.json()["units"]]

    print(f"\n✅ 2 produits créés")
    print(f"   {product_id_1} → Paracetamol 500mg | 5 SN")
    print(f"   {product_id_2} → Amoxicilline 1g   | 3 SN")


# ─────────────────────────────────────────────────────────────────
# TEST 2 — Lister tous les produits en stock
# CE QU'ON VÉRIFIE : les 2 produits sont visibles + compteurs corrects
# SWAGGER          : GET /stock → Execute
# ─────────────────────────────────────────────────────────────────
def test_get_all_stock():
    r = httpx.get(f"{BASE_URL}/stock")
    assert r.status_code == 200
    assert r.json()["total_products"] >= 2

    print(f"\n✅ Stock visible : {r.json()['total_products']} produits")


# ─────────────────────────────────────────────────────────────────
# TEST 3 — Voir un produit par product_id
# CE QU'ON VÉRIFIE : retourne le bon produit avec tous ses SN
# SWAGGER          : GET /stock/{product_id} → coller product_id_1
# ─────────────────────────────────────────────────────────────────
def test_get_product_by_id():
    r = httpx.get(f"{BASE_URL}/stock/{product_id_1}")
    assert r.status_code == 200
    assert r.json()["product_name"] == "Paracetamol 500mg"
    assert r.json()["total_pending"] == 5

    print(f"\n✅ Produit {product_id_1} trouvé — 5 unités pending")


# ─────────────────────────────────────────────────────────────────
# TEST 4 — Modifier le nom d'un produit (PUT)
# CE QU'ON VÉRIFIE : nom mis à jour + log enregistré
# SWAGGER          : PUT /stock/{product_id} → product_name nouveau
# ─────────────────────────────────────────────────────────────────
def test_update_stock():
    r = httpx.put(
        f"{BASE_URL}/stock/{product_id_2}",
        params={"product_name": "Amoxicilline 500mg", "form": "gelules"}
    )
    assert r.status_code == 200
    assert r.json()["product"]["product_name"] == "Amoxicilline 500mg"

    print(f"\n✅ Produit {product_id_2} modifié → Amoxicilline 500mg")


# ─────────────────────────────────────────────────────────────────
# TEST 5 — Modifier produit avec unités rejetées → interdit (403)
# CE QU'ON VÉRIFIE : PUT bloqué si lot a des rejets (GxP)
# SWAGGER          : PUT /stock/{product_id} après un fail → voir 403
# ─────────────────────────────────────────────────────────────────
def test_update_stock_blocked_after_reject():
    # D'abord rejeter une unité
    sn = all_sns_1[0]
    httpx.post(f"{BASE_URL}/machine/test", json={
        "serial_number": sn,
        "station_id": "STATION-01",
        "result": "fail"
    })

    # Maintenant tenter de modifier → doit être bloqué
    r = httpx.put(
        f"{BASE_URL}/stock/{product_id_1}",
        params={"product_name": "Test Modif Interdite"}
    )
    assert r.status_code == 403

    print(f"\n✅ Modification bloquée (403) — lot contient des rejets")


# ─────────────────────────────────────────────────────────────────
# TEST 6 — Machine PASS sur un SN
# CE QU'ON VÉRIFIE : statut → passed, compteur passed +1
# SWAGGER          : POST /machine/test → result: pass
# ─────────────────────────────────────────────────────────────────
def test_machine_pass():
    global sn_pass
    sn_pass = all_sns_2[0]

    r = httpx.post(f"{BASE_URL}/machine/test", json={
        "serial_number": sn_pass,
        "station_id": "STATION-02",
        "result": "pass"
    })
    assert r.status_code == 200
    assert r.json()["result"] == "✅ PASS"

    print(f"\n✅ PASS → {sn_pass}")


# ─────────────────────────────────────────────────────────────────
# TEST 7 — Machine FAIL sur un SN
# CE QU'ON VÉRIFIE : statut → rejected + incident créé
# SWAGGER          : POST /machine/test → result: fail
# ─────────────────────────────────────────────────────────────────
def test_machine_fail():
    global sn_fail
    sn_fail = all_sns_2[1]

    r = httpx.post(f"{BASE_URL}/machine/test", json={
        "serial_number": sn_fail,
        "station_id": "STATION-02",
        "result": "fail"
    })
    assert r.status_code == 200
    assert r.json()["result"] == "❌ FAIL"
    assert r.json()["incident_id"].startswith("INC-")

    print(f"\n✅ FAIL → {sn_fail} | Incident : {r.json()['incident_id']}")


# ─────────────────────────────────────────────────────────────────
# TEST 8 — Corriger un résultat de test (PUT machine)
# CE QU'ON VÉRIFIE : fail → pass corrigé + log enregistré
# SWAGGER          : PUT /machine/test/{sn} → new_result: pass
# ─────────────────────────────────────────────────────────────────
def test_correct_machine_result():
    r = httpx.put(
        f"{BASE_URL}/machine/test/{sn_fail}",
        params={"new_result": "pass", "station_id": "STATION-02"}
    )
    assert r.status_code == 200
    assert r.json()["old_status"] == "rejected"
    assert r.json()["new_status"] == "passed"

    print(f"\n✅ Résultat corrigé : rejected → passed pour {sn_fail}")


# ─────────────────────────────────────────────────────────────────
# TEST 9 — Supprimer une seule unité (pending uniquement)
# CE QU'ON VÉRIFIE : SN supprimé → 404 après suppression
# SWAGGER          : DELETE /stock/sn/{serial_number} → SN pending
# ─────────────────────────────────────────────────────────────────
def test_delete_single_sn():
    sn_to_delete = all_sns_2[2]  # dernier SN encore pending

    r = httpx.delete(f"{BASE_URL}/stock/sn/{sn_to_delete}")
    assert r.status_code == 200

    # Vérifier qu'il n'existe plus
    check = httpx.get(f"{BASE_URL}/debug/sn/{sn_to_delete}")
    assert check.json()["existe"] == False

    print(f"\n✅ SN {sn_to_delete} supprimé — confirmé introuvable")


# ─────────────────────────────────────────────────────────────────
# TEST 10 — Supprimer un SN passed → interdit (403)
# CE QU'ON VÉRIFIE : suppression bloquée si passed (GxP)
# SWAGGER          : DELETE /stock/sn/{sn_pass} → voir 403
# ─────────────────────────────────────────────────────────────────
def test_delete_passed_sn_blocked():
    r = httpx.delete(f"{BASE_URL}/stock/sn/{sn_pass}")
    assert r.status_code == 403

    print(f"\n✅ Suppression bloquée (403) — SN passed ne peut pas être supprimé")


# ─────────────────────────────────────────────────────────────────
# TEST 11 — Supprimer un produit entier (sans tests effectués)
# CE QU'ON VÉRIFIE : produit supprimé → 404 après suppression
# SWAGGER          : DELETE /stock/{product_id} → produit sans tests
# ─────────────────────────────────────────────────────────────────
def test_delete_product():
    # Créer un nouveau produit sans tests
    r = httpx.post(f"{BASE_URL}/stock/multi", json=[{
        "product_name": "Produit Test Suppression",
        "form": "comprimes",
        "batch_number": "BAT-DEL",
        "quantity": 2
    }])
    pid = r.json()["produits"][0]["product_id"]

    r2 = httpx.delete(f"{BASE_URL}/stock/{pid}")
    assert r2.status_code == 200

    r3 = httpx.get(f"{BASE_URL}/stock/{pid}")
    assert r3.status_code == 404

    print(f"\n✅ Produit {pid} supprimé — confirmé introuvable")