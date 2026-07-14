"""
Agent de Stockage MongoDB - SONASID RH System
Stocke les données avec historisation temporelle
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
import json
import os


class AgentStockageMongoDB:
    """
    Agent responsable du stockage des données RH dans MongoDB.
    Gère l'historisation : chaque année crée un snapshot sans écraser l'historique.
    """
    
    def __init__(self, uri: str = "mongodb://localhost:27017", db_name: str = "sonasid_rh"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.rapport = {
            "agent": "agent_stockage_mongodb",
            "timestamp": datetime.now().isoformat(),
            "operations": []
        }
        print(f"🔗 Connecté à MongoDB: {db_name}")
    
    def creer_collections(self):
        """Crée les collections avec index optimisés."""
        print("\n📦 Création des collections...")
        
        # Collection employes - avec historique
        if "employes" not in self.db.list_collection_names():
            self.db.create_collection("employes")
            print("   ✅ Collection 'employes' créée")
        
        # Index sur matricule + annee pour recherche rapide
        self.db.employes.create_index([("MATRICULE", ASCENDING), ("ANNEE_REFERENCE", DESCENDING)])
        self.db.employes.create_index([("STATUT", ASCENDING)])
        self.db.employes.create_index([("COLLÈGE", ASCENDING)])
        print("   ✅ Index créés sur employes")
        
        # Collection mouvements
        if "mouvements" not in self.db.list_collection_names():
            self.db.create_collection("mouvements")
        self.db.mouvements.create_index([("MATRICULE", ASCENDING), ("ANNEE_REFERENCE", DESCENDING)])
        print("   ✅ Collection 'mouvements' prête")
        
        # Collection kpis_annuels
        if "kpis_annuels" not in self.db.list_collection_names():
            self.db.create_collection("kpis_annuels")
        self.db.kpis_annuels.create_index([("annee", DESCENDING)], unique=True)
        print("   ✅ Collection 'kpis_annuels' prête")
        
        # Collection historique_changements
        if "historique_changements" not in self.db.list_collection_names():
            self.db.create_collection("historique_changements")
        print("   ✅ Collection 'historique_changements' prête")
    
    def inserer_employes(self, employes: list, annee: str):
        """
        Insère les employés avec gestion d'historique.
        Si un employé existe déjà, on ajoute un nouveau snapshot pour cette année.
        """
        print(f"\n💾 Insertion de {len(employes)} employés (année {annee})...")
        
        inserted = 0
        updated = 0
        
        for emp in employes:
            matricule = emp.get("MATRICULE")
            
            # Vérifier si l'employé existe déjà pour cette année
            existant = self.db.employes.find_one({
                "MATRICULE": matricule,
                "ANNEE_REFERENCE": annee
            })
            
            if existant:
                # Mettre à jour le snapshot existant
                self.db.employes.update_one(
                    {"_id": existant["_id"]},
                    {"$set": {**emp, "date_mise_a_jour": datetime.now().isoformat()}}
                )
                updated += 1
            else:
                # Nouveau snapshot
                emp["date_insertion"] = datetime.now().isoformat()
                self.db.employes.insert_one(emp)
                inserted += 1
        
        print(f"   ✅ {inserted} nouveaux, {updated} mis à jour")
        self.rapport["operations"].append({
            "collection": "employes",
            "annee": annee,
            "inserted": inserted,
            "updated": updated
        })
    
    def inserer_mouvements(self, mouvements: list, annee: str):
        """Insère les mouvements (recrutements/départs)."""
        print(f"\n💾 Insertion de {len(mouvements)} mouvements (année {annee})...")
        
        # Supprimer les anciens mouvements de cette année pour éviter les doublons
        self.db.mouvements.delete_many({"ANNEE_REFERENCE": annee})
        
        for mov in mouvements:
            mov["date_insertion"] = datetime.now().isoformat()
        
        if mouvements:
            self.db.mouvements.insert_many(mouvements)
        
        print(f"   ✅ {len(mouvements)} mouvements insérés")
        self.rapport["operations"].append({
            "collection": "mouvements",
            "annee": annee,
            "count": len(mouvements)
        })
    
    def inserer_kpis(self, kpis: list, annee: str):
        """Insère les KPIs annuels."""
        print(f"\n💾 Insertion des KPIs (année {annee})...")
        
        for kpi in kpis:
            kpi["date_insertion"] = datetime.now().isoformat()
            self.db.kpis_annuels.update_one(
                {"annee": annee},
                {"$set": kpi},
                upsert=True
            )
        
        print(f"   ✅ KPIs enregistrés")
        self.rapport["operations"].append({
            "collection": "kpis_annuels",
            "annee": annee
        })
    
    def detecter_changements(self, annee_actuelle: str, annee_precedente: str = None):
        """
        Détecte les changements entre deux années.
        Si annee_precedente est None, compare avec l'année précédente disponible.
        """
        print(f"\n🔍 Détection des changements...")
        
        if annee_precedente is None:
            # Trouver l'année précédente
            annees = self.db.employes.distinct("ANNEE_REFERENCE")
            annees = sorted([a for a in annees if a != annee_actuelle])
            if annees:
                annee_precedente = annees[-1]
        
        if not annee_precedente:
            print("   ℹ️ Pas d'année précédente trouvée")
            return []
        
        print(f"   Comparaison: {annee_precedente} → {annee_actuelle}")
        
        changements = []
        
        # Employés présents en N-1 mais pas en N (départs)
        emp_n_1 = set(self.db.employes.distinct("MATRICULE", {"ANNEE_REFERENCE": annee_precedente, "STATUT": "ACTIF"}))
        emp_n = set(self.db.employes.distinct("MATRICULE", {"ANNEE_REFERENCE": annee_actuelle, "STATUT": "ACTIF"}))
        
        departs = emp_n_1 - emp_n
        recrutements = emp_n - emp_n_1
        
        for mat in departs:
            changements.append({
                "type": "DEPART",
                "matricule": mat,
                "annee_n_1": annee_precedente,
                "annee_n": annee_actuelle,
                "date_detection": datetime.now().isoformat()
            })
        
        for mat in recrutements:
            changements.append({
                "type": "RECRUTEMENT",
                "matricule": mat,
                "annee_n_1": annee_precedente,
                "annee_n": annee_actuelle,
                "date_detection": datetime.now().isoformat()
            })
        
        # Changements de statut (promotion, changement de collège...)
        pipeline = [
            {"$match": {"ANNEE_REFERENCE": {"$in": [annee_precedente, annee_actuelle]}}},
            {"$group": {
                "_id": "$MATRICULE",
                "snapshots": {"$push": "$$ROOT"}
            }}
        ]
        
        for doc in self.db.employes.aggregate(pipeline):
            snaps = sorted(doc["snapshots"], key=lambda x: x["ANNEE_REFERENCE"])
            if len(snaps) == 2:
                ancien = snaps[0]
                nouveau = snaps[1]
                
                # Détecter changement de collège
                if ancien.get("COLLÈGE") != nouveau.get("COLLÈGE"):
                    changements.append({
                        "type": "CHANGEMENT_COLLEGE",
                        "matricule": doc["_id"],
                        "ancien": ancien.get("COLLÈGE"),
                        "nouveau": nouveau.get("COLLÈGE"),
                        "annee": annee_actuelle,
                        "date_detection": datetime.now().isoformat()
                    })
        
        # Sauvegarder les changements
        if changements:
            self.db.historique_changements.insert_many(changements)
        
        print(f"   ✅ {len(changements)} changements détectés")
        print(f"      - Départs: {len([c for c in changements if c['type'] == 'DEPART'])}")
        print(f"      - Recrutements: {len([c for c in changements if c['type'] == 'RECRUTEMENT'])}")
        print(f"      - Changements internes: {len([c for c in changements if c['type'] == 'CHANGEMENT_COLLEGE'])}")
        
        return changements
    
    def get_statistiques(self, annee: str = None) -> dict:
        """Retourne les statistiques de la base."""
        if annee is None:
            annee = datetime.now().strftime("%Y")
        
        stats = {
            "annee": annee,
            "total_employes": self.db.employes.count_documents({"ANNEE_REFERENCE": annee}),
            "actifs": self.db.employes.count_documents({"ANNEE_REFERENCE": annee, "STATUT": "ACTIF"}),
            "inactifs": self.db.employes.count_documents({"ANNEE_REFERENCE": annee, "STATUT": "INACTIF"}),
            "hommes": self.db.employes.count_documents({"ANNEE_REFERENCE": annee, "SEXE": "M"}),
            "femmes": self.db.employes.count_documents({"ANNEE_REFERENCE": annee, "SEXE": "F"}),
            "par_college": {},
            "total_mouvements": self.db.mouvements.count_documents({"ANNEE_REFERENCE": annee})
        }
        
        # Par collège
        for doc in self.db.employes.aggregate([
            {"$match": {"ANNEE_REFERENCE": annee}},
            {"$group": {"_id": "$COLLÈGE", "count": {"$sum": 1}}}
        ]):
            stats["par_college"][doc["_id"]] = doc["count"]
        
        return stats
    
    def fermer(self):
        self.client.close()
        print("\n🔒 Connexion MongoDB fermée")


# ============================================================
# TEST COMPLET
# ============================================================

if __name__ == "__main__":
    
    # 1. Charger les données exportées par l'agent d'import
    CHEMIN_EXPORT = r"C:\Users\boujo\sonasid-rh-system\data\export_mongodb.json"
    
    print("="*60)
    print("AGENT DE STOCKAGE MONGODB - TEST")
    print("="*60)
    
    with open(CHEMIN_EXPORT, "r", encoding="utf-8") as f:
        documents = json.load(f)
    
    # 2. Connecter à MongoDB
    agent_db = AgentStockageMongoDB()
    
    # 3. Créer les collections
    agent_db.creer_collections()
    
    # 4. Insérer les données
    annee = documents["metadata"]["annee"]
    
    agent_db.inserer_employes(documents["employes"], annee)
    agent_db.inserer_mouvements(documents["mouvements"], annee)
    agent_db.inserer_kpis(documents["kpis"], annee)
    
    # 5. Afficher les statistiques
    print("\n" + "="*60)
    print("STATISTIQUES MONGODB")
    print("="*60)
    stats = agent_db.get_statistiques(annee)
    for key, val in stats.items():
        print(f"   {key}: {val}")
    
    # 6. Tester la détection de changements (simuler avec la même année pour test)
    # En vrai, on comparera 2024 vs 2025, 2025 vs 2026...
    print("\n📝 Pour tester les changements, importe une 2ème année et compare!")
    
    # 7. Exemple de requête : trouver un employé par matricule
    print("\n🔍 Exemple: Recherche employé matricule 239")
    emp = agent_db.db.employes.find_one({"MATRICULE": 239, "ANNEE_REFERENCE": annee})
    if emp:
        print(f"   {emp.get('NOM')} {emp.get('PRENOM')} - {emp.get('COLLÈGE')} - {emp.get('STATUT')}")
    
    agent_db.fermer()
    
    print("\n🎉 MongoDB prêt! Prochaine étape: Dashboard Power BI")