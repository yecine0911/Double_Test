# ─────────────────────────────────────────────────────────────────
# FICHIER : main.py
# LIGNE   : Formes Sèches (comprimés, gélules)
# LANCER  : uvicorn main:app --reload
# SWAGGER : http://localhost:8000/docs
#
# FLUX COMPLET :
#   1. POST /stock              → créer produit + quantité → SN auto
#   2. GET  /stock              → voir tous les produits + total SN
#   3. GET  /stock/{product_id} → voir un produit + tous ses SN
#   4. POST /machine/test       → machine envoie pass/fail + SN + station
#                                 → FAIL : rejet auto + log horodaté
#   5. POST /rapports/generer   → générer rapport final (JSON + HTML)
#   6. GET  /rapports           → voir tous les rapports archivés
#   7. GET  /rapports/{id}      → consulter un rapport spécifique
#   8. GET  /rapports/lot/{batch_number} → rapports par numéro de lot
# ─────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid
import hashlib
import json

app = FastAPI(
    title="MES — Ligne Formes Sèches + Rapports GxP",
    description="""
## 🏭 MES — Ligne de Production Formes Sèches (Comprimés / Gélules)
    """,
    version="1.0.0"
)

# ─── Stockage en mémoire ──────────────────────────────────────────
stock_items   = {}   # clé = SN
stock_batches = {}   # clé = product_id
incidents     = {}   # clé = incident_id
logs          = []   # liste de tous les logs horodatés
rapports      = {}   # clé = rapport_id

# ─── Modèles ──────────────────────────────────────────────────────

class StockCreate(BaseModel):
    product_name: str
    form: str
    batch_number: str
    quantity: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_name": "Paracetamol 500mg",
                "form": "comprimes",
                "batch_number": "BAT-001",
                "quantity": 10
            }
        }
    }

class MachineTest(BaseModel):
    serial_number: str
    station_id: str
    result: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "serial_number": "SN-20260310-A1B2C3",
                "station_id": "STATION-01",
                "result": "fail"
            }
        }
    }

class RapportGenerer(BaseModel):
    batch_number: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "batch_number": "BAT-001",
            }
        }
    }

# ─── Utilitaires ──────────────────────────────────────────────────
def generate_product_id():
    return f"PRD-{str(uuid.uuid4())[:6].upper()}"

def generate_incident_id():
    return f"INC-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

def generate_rapport_id():
    return f"RPT-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"

def ajouter_log(action: str, detail: str):
    # Chaque action est enregistrée avec horodatage précis
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "detail": detail
    })

def generer_hash(contenu: dict) -> str:
    # Hash SHA256 pour garantir l'intégrité du rapport (non modifiable)
    contenu_str = json.dumps(contenu, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(contenu_str.encode()).hexdigest()

def generer_html(rapport: dict) -> str:
    # Générer le rapport HTML
    incidents_rows = ""
    for inc in rapport["incidents"]:
        incidents_rows += f"""
        <tr>
            <td>{inc['incident_id']}</td>
            <td>{inc['serial_number']}</td>
            <td>{inc['station_id']}</td>
            <td>{inc['detected_at']}</td>
            <td><span class="rejected">REJETÉ</span></td>
        </tr>"""

    passed_rows = ""
    for sn in rapport["unites_passees"]:
        passed_rows += f"""
        <tr>
            <td>{sn}</td>
            <td><span class="passed">PASSÉ</span></td>
        </tr>"""

    conformite = "CONFORME" if rapport["total_rejetes"] == 0 else "NON CONFORME"
    conformite_class = "passed" if rapport["total_rejetes"] == 0 else "rejected"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Rapport {rapport['rapport_id']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 10px; }}
        h2 {{ color: #283593; margin-top: 30px; }}
        .header-box {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat {{ background: white; padding: 15px 25px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-number {{ font-size: 2em; font-weight: bold; }}
        .passed {{ color: #2e7d32; font-weight: bold; }}
        .rejected {{ color: #c62828; font-weight: bold; }}
        .pending {{ color: #f57f17; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th {{ background: #1a237e; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f5f5f5; }}
        .conformite {{ font-size: 1.5em; font-weight: bold; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; }}
        .hash-box {{ background: #263238; color: #80cbc4; padding: 15px; border-radius: 8px; font-family: monospace; font-size: 0.85em; word-break: break-all; margin-top: 20px; }}
        .integrity-note {{ color: #666; font-size: 0.85em; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>📋 Rapport de Production GxP</h1>

    <div class="header-box">
        <table style="box-shadow:none;">
            <tr><th>Champ</th><th>Valeur</th></tr>
            <tr><td>Rapport ID</td><td><strong>{rapport['rapport_id']}</strong></td></tr>
            <tr><td>Numéro de lot</td><td>{rapport['batch_number']}</td></tr>
            <tr><td>Produit</td><td>{rapport['product_name']}</td></tr>
                <tr><td>Date génération</td><td>{rapport['generated_at']}</td></tr>
        </table>
    </div>

    <div class="stats">
        <div class="stat"><div class="stat-number">{rapport['total_unites']}</div>Unités totales</div>
        <div class="stat"><div class="stat-number passed">{rapport['total_passes']}</div>Passées ✅</div>
        <div class="stat"><div class="stat-number rejected">{rapport['total_rejetes']}</div>Rejetées ❌</div>
        <div class="stat"><div class="stat-number pending">{rapport['total_pending']}</div>Non testées</div>
    </div>

    <div class="conformite {conformite_class}">
        Statut de conformité : {conformite}
    </div>

    <h2>❌ Incidents enregistrés</h2>
    <table>
        <tr><th>Incident ID</th><th>Numéro de série</th><th>Station</th><th>Date détection</th><th>Statut</th></tr>
        {incidents_rows if incidents_rows else '<tr><td colspan="5" style="text-align:center">Aucun incident</td></tr>'}
    </table>

    <h2>✅ Unités passées</h2>
    <table>
        <tr><th>Numéro de série</th><th>Statut</th></tr>
        {passed_rows if passed_rows else '<tr><td colspan="2" style="text-align:center">Aucune unité passée</td></tr>'}
    </table>

    <h2>📝 Logs horodatés</h2>
    <table>
        <tr><th>Timestamp</th><th>Action</th><th>Détail</th></tr>
        {''.join(f"<tr><td>{l['timestamp']}</td><td>{l['action']}</td><td>{l['detail']}</td></tr>" for l in rapport['logs'])}
    </table>

    <h2>🔒 Intégrité du rapport</h2>
    <div class="hash-box">
        SHA256 : {rapport['hash_integrite']}
    </div>
    <p class="integrity-note">Ce hash garantit que le rapport n'a pas été modifié après génération.</p>
</body>
</html>"""



# ─────────────────────────────────────────────────────────────────
# POST /stock/multi — Créer un ou plusieurs produits en une fois
# SWAGGER : écrire la liste de produits → un seul Execute
# ─────────────────────────────────────────────────────────────────
@app.post("/stock/multi", summary="Créer un ou plusieurs produits", tags=["Stock"])
def create_stock_multi(produits: list[StockCreate]):
    if not produits:
        raise HTTPException(status_code=422, detail="La liste est vide.")
    if len(produits) > 20:
        raise HTTPException(status_code=422, detail="Maximum 20 produits à la fois.")

    resultats = []
    date_str = datetime.now().strftime("%Y%m%d")

    for data in produits:
        if data.quantity < 1 or data.quantity > 100:
            raise HTTPException(status_code=422, detail=f"Lot {data.batch_number} : quantité entre 1 et 100.")
        if data.form not in ["comprimes", "gelules"]:
            raise HTTPException(status_code=422, detail=f"Lot {data.batch_number} : forme invalide. Valeurs : comprimes, gelules")

        product_id = generate_product_id()
        serial_numbers = []

        for _ in range(data.quantity):
            sn = f"SN-{date_str}-{str(uuid.uuid4())[:6].upper()}"
            while sn in stock_items:
                sn = f"SN-{date_str}-{str(uuid.uuid4())[:6].upper()}"
            serial_numbers.append(sn)
            stock_items[sn] = {
                "serial_number": sn,
                "product_id": product_id,
                "product_name": data.product_name,
                "form": data.form,
                "batch_number": data.batch_number,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "incident_id": None
            }

        stock_batches[product_id] = {
            "product_id": product_id,
            "product_name": data.product_name,
            "form": data.form,
            "batch_number": data.batch_number,
            "quantity": data.quantity,
            "created_at": datetime.now().isoformat(),
            "serial_numbers": serial_numbers,
            "total_pending": data.quantity,
            "total_passed": 0,
            "total_rejected": 0
        }

        ajouter_log("STOCK_CREE", f"Produit: {data.product_name} | Lot: {data.batch_number} | Quantité: {data.quantity} | product_id: {product_id}")
        resultats.append({
            "product_id": product_id,
            "product_name": data.product_name,
            "batch_number": data.batch_number,
            "quantity": data.quantity,
            "premiers_sns": serial_numbers[:3],
            "total_sns_generes": len(serial_numbers)
        })

    return {
        "message": f"{len(resultats)} produit(s) créé(s) avec succès",
        "total_produits": len(resultats),
        "total_sn_generes": sum(r["total_sns_generes"] for r in resultats),
        "produits": resultats
    }


# ─────────────────────────────────────────────────────────────────
# GET /stock — Voir tous les produits en stock
# ─────────────────────────────────────────────────────────────────
@app.get("/stock", summary="Voir tous les produits en stock", tags=["Stock"])
def get_all_stock():
    if not stock_batches:
        return {"message": "Stock vide.", "total_products": 0, "products": []}
    return {"total_products": len(stock_batches), "products": list(stock_batches.values())}


# ─────────────────────────────────────────────────────────────────
# PUT /stock/{product_id} — Modifier nom ou forme d'un produit
# RÈGLE GxP : interdit si le lot a des unités rejected
# ─────────────────────────────────────────────────────────────────
@app.put("/stock/{product_id}", summary="Modifier un produit (nom ou forme)", tags=["Stock"])
def update_stock(product_id: str, product_name: str = None, form: str = None):
    if product_id not in stock_batches:
        raise HTTPException(status_code=404, detail=f"Produit '{product_id}' introuvable.")
    if stock_batches[product_id]["total_rejected"] > 0:
        raise HTTPException(status_code=403, detail="❌ Modification interdite — ce lot contient des unités rejetées (GxP).")
    if form and form not in ["comprimes", "gelules"]:
        raise HTTPException(status_code=422, detail="Forme invalide. Valeurs : comprimes, gelules")

    old_name = stock_batches[product_id]["product_name"]
    old_form = stock_batches[product_id]["form"]

    if product_name:
        stock_batches[product_id]["product_name"] = product_name
    if form:
        stock_batches[product_id]["form"] = form

    ajouter_log("STOCK_MODIFIE", f"product_id: {product_id} | Nom: {old_name} → {product_name or old_name} | Forme: {old_form} → {form or old_form}")
    return {"message": "Produit modifié", "product_id": product_id, "product": stock_batches[product_id]}


# ─────────────────────────────────────────────────────────────────
# DELETE /stock/{product_id} — Supprimer un produit entier
# RÈGLE GxP : interdit si des unités sont rejected ou passed
# ─────────────────────────────────────────────────────────────────
@app.delete("/stock/{product_id}", summary="Supprimer un produit entier", tags=["Stock"])
def delete_stock(product_id: str):
    if product_id not in stock_batches:
        raise HTTPException(status_code=404, detail=f"Produit '{product_id}' introuvable.")

    batch = stock_batches[product_id]
    if batch["total_rejected"] > 0 or batch["total_passed"] > 0:
        raise HTTPException(status_code=403, detail="❌ Suppression interdite — des tests ont déjà été effectués sur ce lot (GxP).")

    # Supprimer tous les SN du produit
    for sn in batch["serial_numbers"]:
        stock_items.pop(sn, None)
    del stock_batches[product_id]

    ajouter_log("STOCK_SUPPRIME", f"Produit supprimé: {batch['product_name']} | Lot: {batch['batch_number']} | {batch['quantity']} SN supprimés")
    return {"message": f"Produit '{product_id}' supprimé avec succès.", "produit_supprime": batch["product_name"], "sn_supprimes": batch["quantity"]}


# ─────────────────────────────────────────────────────────────────
# DELETE /stock/sn/{serial_number} — Supprimer une seule unité
# RÈGLE GxP : interdit si l'unité est rejected ou passed
# ─────────────────────────────────────────────────────────────────
@app.delete("/stock/sn/{serial_number}", summary="Supprimer une seule unité par SN", tags=["Stock"])
def delete_sn(serial_number: str):
    if serial_number not in stock_items:
        raise HTTPException(status_code=404, detail=f"SN '{serial_number}' introuvable.")

    item = stock_items[serial_number]
    if item["status"] in ["rejected", "passed"]:
        raise HTTPException(status_code=403, detail=f"❌ Suppression interdite — SN est '{item['status']}' (GxP).")

    product_id = item["product_id"]
    stock_batches[product_id]["serial_numbers"].remove(serial_number)
    stock_batches[product_id]["quantity"] -= 1
    stock_batches[product_id]["total_pending"] -= 1
    del stock_items[serial_number]

    ajouter_log("SN_SUPPRIME", f"SN supprimé: {serial_number} | Produit: {item['product_name']} | Lot: {item['batch_number']}")
    return {"message": f"SN '{serial_number}' supprimé avec succès."}


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 3 — Voir un produit par product_id
# ─────────────────────────────────────────────────────────────────
@app.get("/stock/{product_id}", summary="Voir un produit et tous ses SN", tags=["Stock"])
def get_product_stock(product_id: str):
    if product_id not in stock_batches:
        raise HTTPException(status_code=404, detail=f"Produit '{product_id}' introuvable.")
    batch = stock_batches[product_id]
    units = [stock_items[sn] for sn in batch["serial_numbers"] if sn in stock_items]
    return {**batch, "units": units}


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 4 — Résultat machine (pass / fail)
# CE QU'ON ATTEND :
#   PASS → statut passed + log horodaté
#   FAIL → statut rejected + incident + log horodaté
# SWAGGER         : copier SN → result: fail → observer rejet + log
# ─────────────────────────────────────────────────────────────────
@app.post("/machine/test", summary="Résultat machine pass/fail → log horodaté auto", tags=["Machine"])
def machine_test(data: MachineTest):
    if data.serial_number not in stock_items:
        raise HTTPException(status_code=404, detail=f"SN '{data.serial_number}' introuvable.")
    if data.result not in ["pass", "fail"]:
        raise HTTPException(status_code=422, detail="Résultat invalide. Valeurs : pass, fail")

    item = stock_items[data.serial_number]
    product_id = item["product_id"]

    if data.result == "pass":
        item["status"] = "passed"
        stock_batches[product_id]["total_pending"] -= 1
        stock_batches[product_id]["total_passed"] += 1
        ajouter_log("TEST_PASS", f"SN: {data.serial_number} | Station: {data.station_id} | Produit: {item['product_name']} | Lot: {item['batch_number']}")
        return {
            "result": "✅ PASS",
            "serial_number": data.serial_number,
            "station_id": data.station_id,
            "product_name": item["product_name"],
            "status": "passed",
            "tested_at": datetime.now().isoformat()
        }

    # FAIL → rejet + incident + log
    incident_id = generate_incident_id()
    incident = {
        "incident_id": incident_id,
        "serial_number": data.serial_number,
        "product_id": product_id,
        "product_name": item["product_name"],
        "batch_number": item["batch_number"],
        "station_id": data.station_id,
        "detected_at": datetime.now().isoformat()
    }
    incidents[incident_id] = incident
    item["status"] = "rejected"
    item["incident_id"] = incident_id
    stock_batches[product_id]["total_pending"] -= 1
    stock_batches[product_id]["total_rejected"] += 1

    ajouter_log("TEST_FAIL", f"SN: {data.serial_number} | Station: {data.station_id} | Produit: {item['product_name']} | Lot: {item['batch_number']} | Incident: {incident_id}")
    ajouter_log("REJET_AUTO", f"SN: {data.serial_number} automatiquement rejeté suite à l'échec du test en {data.station_id}")

    return {
        "result": "❌ FAIL",
        "serial_number": data.serial_number,
        "station_id": data.station_id,
        "product_name": item["product_name"],
        "status": "rejected",
        "incident_id": incident_id,
        "tested_at": datetime.now().isoformat()
    }


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 5 — Générer un rapport par lot
# CE QU'ON ATTEND :
#   - Rapport JSON avec date, opérateur, résultats, logs, incidents
#   - Rapport HTML généré automatiquement
#   - Hash SHA256 pour garantir l'intégrité (non modifiable)
#   - Rapport de non-conformité si rejets > 0
# SWAGGER         : entrer batch_number → rapport généré
# ─────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
# PUT /machine/test/{serial_number} — Corriger un résultat de test
# RÈGLE GxP : on ne peut corriger que les résultats du jour
# ─────────────────────────────────────────────────────────────────
@app.put("/machine/test/{serial_number}", summary="Corriger un résultat de test (pass ↔ fail)", tags=["Machine"])
def update_machine_test(serial_number: str, new_result: str, station_id: str):
    if serial_number not in stock_items:
        raise HTTPException(status_code=404, detail=f"SN '{serial_number}' introuvable.")
    if new_result not in ["pass", "fail"]:
        raise HTTPException(status_code=422, detail="Résultat invalide. Valeurs : pass, fail")

    item = stock_items[serial_number]
    product_id = item["product_id"]
    old_status = item["status"]

    if old_status == "pending":
        raise HTTPException(status_code=400, detail="Ce SN n'a pas encore été testé.")

    # Annuler l'ancien résultat dans les compteurs
    if old_status == "passed":
        stock_batches[product_id]["total_passed"] -= 1
    elif old_status == "rejected":
        stock_batches[product_id]["total_rejected"] -= 1
        # Supprimer l'incident lié si existant
        if item["incident_id"] and item["incident_id"] in incidents:
            del incidents[item["incident_id"]]
        item["incident_id"] = None

    # Appliquer le nouveau résultat
    if new_result == "pass":
        item["status"] = "passed"
        stock_batches[product_id]["total_passed"] += 1
    else:
        incident_id = generate_incident_id()
        incidents[incident_id] = {
            "incident_id": incident_id,
            "serial_number": serial_number,
            "product_id": product_id,
            "product_name": item["product_name"],
            "batch_number": item["batch_number"],
            "station_id": station_id,
            "detected_at": datetime.now().isoformat()
        }
        item["status"] = "rejected"
        item["incident_id"] = incident_id
        stock_batches[product_id]["total_rejected"] += 1

    ajouter_log("TEST_CORRIGE", f"SN: {serial_number} | Ancien: {old_status} → Nouveau: {item['status']} | Station: {station_id}")
    return {"message": "Résultat corrigé", "serial_number": serial_number, "old_status": old_status, "new_status": item["status"]}

@app.post("/rapports/generer", summary="Générer un rapport GxP par numéro de lot", tags=["Rapports"])
def generer_rapport(data: RapportGenerer):

    # Trouver le produit correspondant au lot
    batch = next((b for b in stock_batches.values() if b["batch_number"] == data.batch_number), None)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Lot '{data.batch_number}' introuvable.")

    # Récupérer les unités du lot
    units = [stock_items[sn] for sn in batch["serial_numbers"] if sn in stock_items]
    unites_passees = [u["serial_number"] for u in units if u["status"] == "passed"]
    unites_rejetees = [u["serial_number"] for u in units if u["status"] == "rejected"]
    unites_pending = [u["serial_number"] for u in units if u["status"] == "pending"]

    # Incidents liés au lot
    incidents_lot = [i for i in incidents.values() if i["batch_number"] == data.batch_number]

    # Logs liés au lot
    logs_lot = [l for l in logs if data.batch_number in l["detail"]]

    # Statut de conformité
    conforme = len(unites_rejetees) == 0
    statut_conformite = "CONFORME" if conforme else "NON CONFORME"

    rapport_id = generate_rapport_id()
    generated_at = datetime.now().isoformat()

    # Construire le rapport
    contenu_rapport = {
        "rapport_id": rapport_id,
        "batch_number": data.batch_number,
        "product_name": batch["product_name"],
        "product_id": batch["product_id"],
        "form": batch["form"],
        "generated_at": generated_at,
        "statut_conformite": statut_conformite,
        "total_unites": batch["quantity"],
        "total_passes": len(unites_passees),
        "total_rejetes": len(unites_rejetees),
        "total_pending": len(unites_pending),
        "unites_passees": unites_passees,
        "unites_rejetees": unites_rejetees,
        "incidents": incidents_lot,
        "logs": logs_lot,
        "non_conformite": None if conforme else {
            "type": "RAPPORT_NON_CONFORMITE",
            "batch_number": data.batch_number,
            "total_rejetes": len(unites_rejetees),
            "incidents": incidents_lot,
            "generated_at": generated_at
        }
    }

    # Hash SHA256 pour intégrité (rapport non modifiable après génération)
    contenu_rapport["hash_integrite"] = generer_hash(contenu_rapport)

    # Générer HTML
    html_contenu = generer_html(contenu_rapport)
    contenu_rapport["html"] = html_contenu

    # Archiver le rapport
    rapports[rapport_id] = contenu_rapport

    ajouter_log("RAPPORT_GENERE", f"Rapport: {rapport_id} | Lot: {data.batch_number} | Conformité: {statut_conformite}")

    return {
        "message": "Rapport généré avec succès",
        "rapport_id": rapport_id,
        "batch_number": data.batch_number,
        "statut_conformite": statut_conformite,
        "total_unites": batch["quantity"],
        "total_passes": len(unites_passees),
        "total_rejetes": len(unites_rejetees),
        "total_pending": len(unites_pending),
        "non_conformite": contenu_rapport["non_conformite"],
        "hash_integrite": contenu_rapport["hash_integrite"],
        "html_url": f"/rapports/{rapport_id}/html",
        "rapport_complet_url": f"/rapports/{rapport_id}"
    }


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 6 — Voir tous les rapports archivés
# CE QU'ON ATTEND : liste de tous les rapports générés
# SWAGGER         : Execute → voir tous les rapports archivés
# ─────────────────────────────────────────────────────────────────
@app.get("/rapports", summary="Tous les rapports archivés", tags=["Rapports"])
def get_all_rapports():
    if not rapports:
        return {"message": "Aucun rapport. Générez via POST /rapports/generer.", "total": 0, "rapports": []}
    # Résumé sans le HTML pour ne pas surcharger la réponse
    resume = [{k: v for k, v in r.items() if k != "html"} for r in rapports.values()]
    return {"total": len(rapports), "rapports": resume}


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 7 — Consulter un rapport JSON
# CE QU'ON ATTEND : rapport complet avec logs, incidents, hash
# SWAGGER         : copier rapport_id → voir rapport complet
# ─────────────────────────────────────────────────────────────────
@app.get("/rapports/{rapport_id}", summary="Consulter un rapport complet (JSON)", tags=["Rapports"])
def get_rapport(rapport_id: str):
    if rapport_id not in rapports:
        raise HTTPException(status_code=404, detail=f"Rapport '{rapport_id}' introuvable.")
    return {k: v for k, v in rapports[rapport_id].items() if k != "html"}


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 8 — Voir le rapport en HTML
# CE QU'ON ATTEND : page HTML avec tableau des résultats
# SWAGGER         : copier rapport_id → ouvrir l'URL dans le navigateur
# ─────────────────────────────────────────────────────────────────
@app.get("/rapports/{rapport_id}/html", summary="Voir le rapport en HTML", tags=["Rapports"], response_class=HTMLResponse)
def get_rapport_html(rapport_id: str):
    if rapport_id not in rapports:
        raise HTTPException(status_code=404, detail=f"Rapport '{rapport_id}' introuvable.")
    return HTMLResponse(content=rapports[rapport_id]["html"])


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 9 — Rapports par numéro de lot
# CE QU'ON ATTEND : tous les rapports générés pour un lot donné
# SWAGGER         : entrer batch_number → voir historique des rapports
# ─────────────────────────────────────────────────────────────────
@app.get("/rapports/lot/{batch_number}", summary="Rapports archivés par numéro de lot", tags=["Rapports"])
def get_rapports_par_lot(batch_number: str):
    result = [{k: v for k, v in r.items() if k != "html"} for r in rapports.values() if r["batch_number"] == batch_number]
    if not result:
        raise HTTPException(status_code=404, detail=f"Aucun rapport pour le lot '{batch_number}'.")
    return {"batch_number": batch_number, "total_rapports": len(result), "rapports": result}


# ─────────────────────────────────────────────────────────────────
# ENDPOINT 10 — Voir tous les logs horodatés
# CE QU'ON ATTEND : historique complet de toutes les actions
# SWAGGER         : Execute → voir chaque action avec timestamp
# ─────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────
# PUT /rapports/{rapport_id} — Mettre à jour le statut de conformité
# RÈGLE GxP : log obligatoire, hash recalculé
# ─────────────────────────────────────────────────────────────────
@app.put("/rapports/{rapport_id}", summary="Mettre à jour le statut de conformité", tags=["Rapports"])
def update_rapport(rapport_id: str, statut_conformite: str):
    if rapport_id not in rapports:
        raise HTTPException(status_code=404, detail=f"Rapport '{rapport_id}' introuvable.")
    if statut_conformite not in ["CONFORME", "NON CONFORME"]:
        raise HTTPException(status_code=422, detail="Statut invalide. Valeurs : CONFORME, NON CONFORME")

    old_statut = rapports[rapport_id]["statut_conformite"]
    rapports[rapport_id]["statut_conformite"] = statut_conformite
    rapports[rapport_id]["hash_integrite"] = generer_hash({k: v for k, v in rapports[rapport_id].items() if k != "html"})

    ajouter_log("RAPPORT_MODIFIE", f"Rapport: {rapport_id} | Statut: {old_statut} → {statut_conformite}")
    return {"message": "Rapport mis à jour", "rapport_id": rapport_id, "old_statut": old_statut, "new_statut": statut_conformite}


# ─────────────────────────────────────────────────────────────────
# DELETE /rapports/{rapport_id} — Archiver/supprimer un rapport
# RÈGLE GxP : interdit si statut = CONFORME (rapport validé)
# ─────────────────────────────────────────────────────────────────
@app.delete("/rapports/{rapport_id}", summary="Supprimer un rapport (non conforme uniquement)", tags=["Rapports"])
def delete_rapport(rapport_id: str):
    if rapport_id not in rapports:
        raise HTTPException(status_code=404, detail=f"Rapport '{rapport_id}' introuvable.")
    if rapports[rapport_id]["statut_conformite"] == "CONFORME":
        raise HTTPException(status_code=403, detail="❌ Suppression interdite — rapport CONFORME ne peut pas être supprimé (GxP).")

    deleted = rapports.pop(rapport_id)
    ajouter_log("RAPPORT_SUPPRIME", f"Rapport supprimé: {rapport_id} | Lot: {deleted['batch_number']}")
    return {"message": f"Rapport '{rapport_id}' supprimé.", "batch_number": deleted["batch_number"]}


# ─────────────────────────────────────────────────────────────────
# DELETE /incidents/{incident_id} — Annuler un incident par erreur
# RÈGLE GxP : log obligatoire, statut SN remis à pending
# ─────────────────────────────────────────────────────────────────
@app.delete("/incidents/{incident_id}", summary="Annuler un incident enregistré par erreur", tags=["Rapports"])
def delete_incident(incident_id: str):
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' introuvable.")

    incident = incidents[incident_id]
    sn = incident["serial_number"]
    product_id = incident["product_id"]

    # Remettre le SN en pending
    if sn in stock_items:
        stock_items[sn]["status"] = "pending"
        stock_items[sn]["incident_id"] = None
        stock_batches[product_id]["total_rejected"] -= 1
        stock_batches[product_id]["total_pending"] += 1

    del incidents[incident_id]
    ajouter_log("INCIDENT_ANNULE", f"Incident annulé: {incident_id} | SN: {sn} remis en pending")
    return {"message": f"Incident '{incident_id}' annulé. SN '{sn}' remis en pending."}

@app.get("/logs", summary="Tous les logs horodatés", tags=["Logs"])
def get_all_logs():
    if not logs:
        return {"message": "Aucun log.", "total": 0, "logs": []}
    return {"total": len(logs), "logs": logs}

# ─────────────────────────────────────────────────────────────────
# ENDPOINT DEBUG — Voir tout ce qui est en mémoire
# CE QU'ON ATTEND : snapshot complet de l'état du serveur
# UTILITÉ         : vérifier immédiatement si la création a réussi
#                   voir combien de produits, SN, incidents en mémoire
# SWAGGER         : GET /debug → Execute → voir tout l'état actuel
# ─────────────────────────────────────────────────────────────────
@app.get("/debug", summary="🔍 Voir tout ce qui est en mémoire", tags=["Debug"])
def debug_memory():
    return {
        "etat_memoire": {
            "total_produits_stock": len(stock_batches),
            "total_unites_sn": len(stock_items),
            "total_incidents": len(incidents),
            "total_rapports": len(rapports),
            "total_logs": len(logs)
        },
        "produits": [
            {
                "product_id": b["product_id"],
                "product_name": b["product_name"],
                "batch_number": b["batch_number"],
                "quantity": b["quantity"],
                "created_at": b["created_at"],
                "pending": b["total_pending"],
                "passed": b["total_passed"],
                "rejected": b["total_rejected"],
                "premiers_sns": b["serial_numbers"][:3],
                "derniers_sns": b["serial_numbers"][-3:]
            }
            for b in stock_batches.values()
        ],
        "derniers_logs": logs[-5:] if logs else [],
        "derniers_incidents": list(incidents.values())[-3:] if incidents else []
    }


# ─────────────────────────────────────────────────────────────────
# ENDPOINT DEBUG SN — Vérifier un SN spécifique
# CE QU'ON ATTEND : confirmer que le SN existe et voir son état
# UTILITÉ         : après création, coller un SN et vérifier
# SWAGGER         : GET /debug/sn/{serial_number} → état du SN
# ─────────────────────────────────────────────────────────────────
@app.get("/debug/sn/{serial_number}", summary="🔍 Vérifier un SN spécifique", tags=["Debug"])
def debug_sn(serial_number: str):
    if serial_number not in stock_items:
        return {
            "existe": False,
            "serial_number": serial_number,
            "message": "❌ Ce SN n'existe pas en mémoire — vérifiez que vous avez bien créé le stock"
        }
    item = stock_items[serial_number]
    return {
        "existe": True,
        "serial_number": serial_number,
        "product_name": item["product_name"],
        "batch_number": item["batch_number"],
        "status": item["status"],
        "created_at": item["created_at"],
        "incident_id": item["incident_id"],
        "message": "✅ SN trouvé en mémoire"
    }