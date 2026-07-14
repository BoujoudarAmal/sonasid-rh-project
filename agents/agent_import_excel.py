"""
Agent d'Import Excel - SONASID RH System v2
Historisation + détection des changements année N vs N-1
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import os


class AgentImportExcel:
    def __init__(self, file_path: str, annee_reference: str = None):
        self.file_path = file_path
        self.annee = annee_reference or datetime.now().strftime("%Y")
        self.dataframes = {}
        self.rapport = {
            "agent": "agent_import_excel",
            "annee_reference": self.annee,
            "timestamp": datetime.now().isoformat(),
            "fichier": os.path.basename(file_path),
            "feuilles_trouvees": [],
            "lignes_importees": {},
            "erreurs": [],
            "doublons_detectes": 0,
            "valeurs_manquantes": {},
            "changements_detectes": []
        }
    
    def charger_fichier(self) -> dict:
        print(f"📂 Chargement du fichier: {self.file_path}")
        try:
            xls = pd.ExcelFile(self.file_path)
            self.rapport["feuilles_trouvees"] = xls.sheet_names
            print(f"✅ Feuilles trouvées: {xls.sheet_names}")
            
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(self.file_path, sheet_name=sheet_name)
                self.dataframes[sheet_name] = df
                self.rapport["lignes_importees"][sheet_name] = len(df)
                print(f"   📄 {sheet_name}: {len(df)} lignes, {len(df.columns)} colonnes")
            
            return self.dataframes
            
        except Exception as e:
            self.rapport["erreurs"].append(str(e))
            print(f"❌ Erreur: {e}")
            raise
    
    def nettoyer_effectif(self) -> pd.DataFrame:
        if "EFFECTIF" not in self.dataframes:
            raise ValueError("Feuille 'EFFECTIF' non trouvée!")
        
        print("\n🔧 Nettoyage de la feuille EFFECTIF...")
        df = self.dataframes["EFFECTIF"].copy()
        
        # Supprimer ligne d'en-tête dupliquée
        if df.iloc[0].astype(str).str.contains("MATRICULE|Matricule").any():
            df = df.iloc[1:].reset_index(drop=True)
            print("   🗑️ Ligne d'en-tête dupliquée supprimée")
        
        # Renommer colonnes
        df.columns = [str(col).strip().upper().replace(" ", "_") for col in df.columns]
        
        # Supprimer doublons
        doublons = df.duplicated(subset=["MATRICULE"], keep="first").sum()
        df = df.drop_duplicates(subset=["MATRICULE"], keep="first")
        self.rapport["doublons_detectes"] = int(doublons)
        print(f"   🗑️ {doublons} doublons supprimés")
        
        # Convertir dates Excel
        date_columns = ["DEB_CONTRAT", "DATE_DE_NAISSANCE", "DATE_RETRAITE", "DATE_DE_DÉPART"]
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df[col] = pd.to_datetime(df[col], unit="D", origin="1899-12-30", errors="coerce")
                print(f"   📅 {col} convertie")
        
        # Convertir numériques
        for col in ["ÂGE", "ANCIENNITE", "H/F"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Normaliser sexe
        if "SEXE" in df.columns:
            df["SEXE"] = df["SEXE"].astype(str).str.strip().str.upper()
            df["SEXE"] = df["SEXE"].replace({
                "MR": "M", "M": "M", "HOMME": "M", "H": "M",
                "MME": "F", "MLLE": "F", "F": "F", "FEMME": "F", "MELLE": "F"
            })
            print("   ⚧ Sexe normalisé")
        
        # Normaliser type contrat
        if "TYPE_CONTRAT" in df.columns:
            df["TYPE_CONTRAT"] = df["TYPE_CONTRAT"].astype(str).str.strip().str.upper()
            # Remplacer NaN par le type déduit du statut
            df.loc[df["TYPE_CONTRAT"].isin(["NAN", "NONE", "NAT"]), "TYPE_CONTRAT"] = None
            print("   📋 Type de contrat normalisé")
        
        # Créer statut
        if "TOUJOURS_À_LA_SONASID_LA_SONASID" in df.columns:
            df["STATUT"] = df["TOUJOURS_À_LA_SONASID_LA_SONASID"].apply(
                lambda x: "ACTIF" if str(x) == "1" else "INACTIF"
            )
            # Pour les inactifs sans type contrat, mettre le motif comme info
            df.loc[(df["STATUT"] == "INACTIF") & (df["TYPE_CONTRAT"].isna()), "TYPE_CONTRAT"] = "INACTIF"
            print("   🟢 Statut ACTIF/INACTIF créé")
        
        # Ajouter année de référence
        df["ANNEE_REFERENCE"] = self.annee
        
        # Créer snapshot_id unique
        df["SNAPSHOT_ID"] = df["MATRICULE"].astype(str) + "_" + self.annee
        
        # Valeurs manquantes
        missing = df.isnull().sum()
        self.rapport["valeurs_manquantes"] = {
            col: int(count) for col, count in missing.items() if count > 0
        }
        
        self.dataframes["EFFECTIF_NETTOYE"] = df
        print(f"✅ {len(df)} employés nettoyés")
        return df
    
    def nettoyer_mouvements(self) -> pd.DataFrame:
        if "mouvement" not in self.dataframes:
            print("⚠️ Feuille 'mouvement' non trouvée")
            return None
        
        print("\n🔧 Nettoyage mouvement...")
        df = self.dataframes["mouvement"].copy()
        
        if str(df.iloc[0, 0]) == "Matricule":
            df = df.iloc[1:].reset_index(drop=True)
        
        df.columns = [str(col).strip().upper().replace(" ", "_") for col in df.columns]
        
        for col in ["DATE_RECRUTEMENT", "DATE_DEPART"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df[col] = pd.to_datetime(df[col], unit="D", origin="1899-12-30", errors="coerce")
        
        df["ANNEE_REFERENCE"] = self.annee
        self.dataframes["MOUVEMENT_NETTOYE"] = df
        print(f"✅ {len(df)} mouvements nettoyés")
        return df
    
    def extraire_kpi_tdb(self) -> dict:
        """Extrait les KPIs du tableau de bord."""
        if "TDB" not in self.dataframes:
            return {}
        
        print("\n📊 Extraction KPIs du TDB...")
        df = self.dataframes["TDB"]
        
        # Les KPIs sont dans les premières lignes
        kpis = {
            "turnover": None,
            "cdi": None,
            "anapec": None,
            "encadrement_pct": None,
            "seniorite_moyenne": None,
            "recrutements": None,
            "effectif_total": None,
            "hommes": None,
            "femmes": None,
            "annee": self.annee
        }
        
        try:
            # Chercher les valeurs dans le TDB
            for idx, row in df.iterrows():
                row_str = str(row.values)
                if "Turnover" in row_str:
                    kpis["turnover"] = float(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                elif "CDI" in row_str:
                    kpis["cdi"] = int(row.iloc[1]) if pd.notna(row.iloc[1]) else None
                elif "ANAPEC" in row_str:
                    kpis["anapec"] = int(row.iloc[1]) if pd.notna(row.iloc[1]) else None
        except:
            pass
        
        self.dataframes["KPI_TDB"] = pd.DataFrame([kpis])
        print(f"   KPIs extraits: {kpis}")
        return kpis
    
    def preparer_documents_mongodb(self) -> dict:
        """
        Convertit les DataFrames en documents MongoDB avec historisation.
        """
        print("\n📦 Préparation des documents MongoDB...")
        
        documents = {
            "employes": [],
            "mouvements": [],
            "kpis": [],
            "metadata": {
                "annee": self.annee,
                "date_import": datetime.now().isoformat(),
                "fichier_source": os.path.basename(self.file_path),
                "total_employes": 0,
                "total_actifs": 0,
                "total_inactifs": 0
            }
        }
        
        # 1. Documents employés (avec snapshot)
        df_emp = self.dataframes.get("EFFECTIF_NETTOYE")
        if df_emp is not None:
            for _, row in df_emp.iterrows():
                doc = row.to_dict()
                # Nettoyer les valeurs NaN
                doc = {k: (None if pd.isna(v) else v) for k, v in doc.items()}
                # Convertir les dates en string ISO
                for k, v in doc.items():
                    if isinstance(v, pd.Timestamp):
                        doc[k] = v.isoformat()
                    elif isinstance(v, (np.integer, np.floating)):
                        doc[k] = float(v) if isinstance(v, np.floating) else int(v)
                documents["employes"].append(doc)
            
            documents["metadata"]["total_employes"] = len(documents["employes"])
            documents["metadata"]["total_actifs"] = sum(1 for e in documents["employes"] if e.get("STATUT") == "ACTIF")
            documents["metadata"]["total_inactifs"] = sum(1 for e in documents["employes"] if e.get("STATUT") == "INACTIF")
        
        # 2. Documents mouvements
        df_mov = self.dataframes.get("MOUVEMENT_NETTOYE")
        if df_mov is not None:
            for _, row in df_mov.iterrows():
                doc = row.to_dict()
                doc = {k: (None if pd.isna(v) else v) for k, v in doc.items()}
                for k, v in doc.items():
                    if isinstance(v, pd.Timestamp):
                        doc[k] = v.isoformat()
                documents["mouvements"].append(doc)
        
        # 3. KPIs
        kpis = self.extraire_kpi_tdb()
        if kpis:
            documents["kpis"].append(kpis)
        
        print(f"   📄 {len(documents['employes'])} employes")
        print(f"   📄 {len(documents['mouvements'])} mouvements")
        print(f"   📄 {len(documents['kpis'])} KPIs")
        
        return documents
    
    def generer_rapport(self) -> dict:
        self.rapport["timestamp_fin"] = datetime.now().isoformat()
        return self.rapport
    
    def sauvegarder_rapport(self, chemin: str = "data/rapport_import.json"):
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(self.rapport, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n📝 Rapport: {chemin}")
    
    def sauvegarder_json(self, documents: dict, chemin: str = "data/export_mongodb.json"):
        """Sauvegarde les documents prêts pour MongoDB."""
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 Export MongoDB: {chemin}")


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    
    CHEMIN_FICHIER = r"C:\Users\boujo\sonasid-rh-system\data\TDB_NADOR 09-2025.xlsx"
    
    # Créer l'agent avec l'année 2025
    agent = AgentImportExcel(CHEMIN_FICHIER, annee_reference="2025")
    
    # 1. Charger
    agent.charger_fichier()
    
    # 2. Nettoyer
    df_effectif = agent.nettoyer_effectif()
    df_mouvements = agent.nettoyer_mouvements()
    
    # 3. Préparer documents MongoDB
    documents = agent.preparer_documents_mongodb()
    
    # 4. Afficher stats
    print("\n" + "="*60)
    print("RÉSULTAT FINAL")
    print("="*60)
    print(f"\n📊 Employés: {documents['metadata']['total_employes']}")
    print(f"   🟢 Actifs: {documents['metadata']['total_actifs']}")
    print(f"   🔴 Inactifs: {documents['metadata']['total_inactifs']}")
    print(f"\n📈 Répartition par collège:")
    print(df_effectif["COLLÈGE"].value_counts())
    print(f"\n📈 Répartition par tranche d'âge:")
    print(df_effectif["PYRAMIDE_AGE"].value_counts())
    
    # 5. Sauvegarder
    agent.sauvegarder_json(documents)
    agent.sauvegarder_rapport()
    
    print("\n🎉 Terminé! Prochaine étape: MongoDB")