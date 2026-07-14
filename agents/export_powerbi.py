"""
Export MongoDB → CSV pour Power BI
"""

import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import os


def exporter_pour_powerbi():
    client = MongoClient("mongodb://localhost:27017")
    db = client["sonasid_rh"]
    
    print("📤 Export pour Power BI...")
    
    # 1. Export employes
    employes = list(db.employes.find({}, {"_id": 0}))
    df_emp = pd.DataFrame(employes)
    
    print(f"   Colonnes disponibles: {list(df_emp.columns)}")
    
    # Convertir les dates
    for col in df_emp.columns:
        if "date" in col.lower() or "dt_" in col.lower():
            df_emp[col] = pd.to_datetime(df_emp[col], errors="coerce")
    
    chemin_emp = "data/employes_powerbi.csv"
    df_emp.to_csv(chemin_emp, index=False, encoding="utf-8-sig")
    print(f"   ✅ {len(df_emp)} employes → {chemin_emp}")
    
    # 2. Export mouvements
    mouvements = list(db.mouvements.find({}, {"_id": 0}))
    if mouvements:
        df_mov = pd.DataFrame(mouvements)
        chemin_mov = "data/mouvements_powerbi.csv"
        df_mov.to_csv(chemin_mov, index=False, encoding="utf-8-sig")
        print(f"   ✅ {len(df_mov)} mouvements → {chemin_mov}")
    else:
        print("   ⚠️ Pas de mouvements")
        df_mov = pd.DataFrame()
    
    # 3. Export KPIs agrégés
    stats = {
        "annee": ["2025"],
        "total_employes": [len(df_emp)],
        "actifs": [len(df_emp[df_emp["STATUT"] == "ACTIF"])],
        "inactifs": [len(df_emp[df_emp["STATUT"] == "INACTIF"])],
        "hommes": [len(df_emp[df_emp["SEXE"] == "M"])],
        "femmes": [len(df_emp[df_emp["SEXE"] == "F"])],
        "cdi": [len(df_emp[df_emp["TYPE_CONTRAT"] == "CDI"])],
        "anapec": [len(df_emp[df_emp["TYPE_CONTRAT"] == "ANAPEC"])],
        "employes_college": [len(df_emp[df_emp["COLLÈGE"] == "Employé"])],
        "maitrise_college": [len(df_emp[df_emp["COLLÈGE"] == "Maitrise"])],
        "cadre_college": [len(df_emp[df_emp["COLLÈGE"] == "Cadre"])],
    }
    
    # Âge moyen (uniquement les > 0)
    age_col = "ÂGE" if "ÂGE" in df_emp.columns else None
    if age_col:
        stats["age_moyen"] = [df_emp[df_emp[age_col] > 0][age_col].mean()]
    else:
        stats["age_moyen"] = [None]
    
    # Ancienneté moyenne
    anciennete_cols = [c for c in df_emp.columns if "ANCIEN" in c.upper()]
    if anciennete_cols:
        col_anc = anciennete_cols[0]
        stats["anciennete_moyenne"] = [df_emp[df_emp[col_anc] > 0][col_anc].mean()]
    else:
        stats["anciennete_moyenne"] = [None]
    
    # Turnover (départs / effectif moyen)
    nb_departs = len(df_mov[df_mov.get("DATE_DEPART").notna()]) if not df_mov.empty and "DATE_DEPART" in df_mov.columns else 0
    effectif_moyen = stats["actifs"][0] + stats["inactifs"][0]
    stats["turnover"] = [round(nb_departs / effectif_moyen, 4) if effectif_moyen > 0 else 0]
    
    df_kpi = pd.DataFrame(stats)
    chemin_kpi = "data/kpis_powerbi.csv"
    df_kpi.to_csv(chemin_kpi, index=False, encoding="utf-8-sig")
    print(f"   ✅ KPIs → {chemin_kpi}")
    
    # 4. Export pyramide âge détaillée
    if "PYRAMIDE_AGE" in df_emp.columns and "SEXE" in df_emp.columns:
        pyramide = df_emp[df_emp["STATUT"] == "ACTIF"].groupby(["PYRAMIDE_AGE", "SEXE"]).size().reset_index(name="effectif")
        chemin_pyramide = "data/pyramide_age_powerbi.csv"
        pyramide.to_csv(chemin_pyramide, index=False, encoding="utf-8-sig")
        print(f"   ✅ Pyramide âge → {chemin_pyramide}")
    
    client.close()
    print("\n🎉 Export terminé ! Fichiers prêts pour Power BI")
    print("\n📁 Fichiers créés dans data/:")
    for f in os.listdir("data"):
        if f.endswith(".csv"):
            print(f"   - {f}")


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    exporter_pour_powerbi()