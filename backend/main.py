from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pymongo import MongoClient
from datetime import datetime
from typing import List
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

EXCEL_PATH = os.path.join(current_dir, "data", "candidats_export.xlsx")

from agents.agent_cv import AgentTraitementCV

app = FastAPI(title="SONASID RH Platform - Forum", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    db = client["sonasid_rh"]
    client.server_info()
    print("🟢 Connexion à MongoDB réussie.")
except Exception as e:
    print(f"⚠️ Erreur de connexion MongoDB : {e}")

# Préparation automatique de l'arborescence des dossiers requis
os.makedirs(os.path.join(current_dir, "uploads", "cv"), exist_ok=True)
os.makedirs(os.path.join(current_dir, "data"), exist_ok=True)

app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/", response_class=HTMLResponse)
async def public_home():
    return FileResponse("../frontend/public/index.html")
@app.post("/api/upload")
async def upload_annuel(file: UploadFile = File(...)):
    try:
        # Sauvegarde temporaire du fichier Excel
        temp_path = os.path.join(current_dir, "uploads", f"temp_{file.filename}")
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        
        # ICI : Ajoute ton code de traitement Excel
        return {
            "status": "success",
            "nouveau_effectif": 0,
            "ancien_effectif": 0,
            "nouveaux": [],
            "departs": [],
            "changements": [],
            "annee": "2025"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/public/cv")
async def upload_cv_multiple_forum(
    files: List[UploadFile] = File(..., alias="files"),
    poste_vise: str = Form("Non spécifié")
):
    resultats = {"succes": 0, "erreurs": 0}
    
    print(f"📥 Reçu : {len(files)} fichier(s) à traiter.")
    
    for file in files:
        temp_path = None
        try:
            ext = os.path.splitext(file.filename)[1].lower().strip()
            valid_ext = ['.pdf', '.docx', '.doc', '.txt']
            
            if ext not in valid_ext:
                print(f"❌ Format refusé pour {file.filename} : {ext}")
                resultats["erreurs"] += 1
                continue
            
            safe_name = file.filename.replace(' ', '_')
            temp_path = os.path.join(current_dir, "uploads", "cv", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}")
            
            content = await file.read()
            with open(temp_path, "wb") as f:
                f.write(content)
            await file.close()
            
            agent = AgentTraitementCV(temp_path)
            informations = agent.traiter()
            score = agent.calculer_score(poste_vise)
            
            candidat = {
                "Nom": informations.get("Nom", "FORUM"),
                "Prénom": informations.get("Prénom", "Inconnu"),
                "Email": informations.get("Email", "Non détecté"),
                "Téléphone": informations.get("Téléphone", "Non détecté"),
                "Profil": informations.get("Profil", ""),
                "Compétences": informations.get("Compétences", ""),
                "Diplômes": informations.get("Diplômes", ""),
                "poste_vise": poste_vise,
                "score": score,
                "cv_path": temp_path,
                "date_depot": datetime.now().isoformat(),
                "statut": "Nouveau"
            }
            
            db.candidats.insert_one(candidat)
            resultats["succes"] += 1
            print(f"✅ Candidat enregistré avec succès : {candidat['Nom']} {candidat['Prénom']}")
            
        except Exception as e:
            resultats["erreurs"] += 1
            print(f"💥 Erreur lors de l'intégration du fichier {file.filename} : {e}")

    # Mise à jour globale du fichier Excel de suivi
    try:
        tous_candidats = list(db.candidats.find({}, {"_id": 0}))
        AgentTraitementCV.exporter_excel(tous_candidats, EXCEL_PATH)
        print("📊 Fichier Excel mis à jour.")
    except Exception as e:
        print(f"⚠️ Erreur lors de l'écriture Excel (Vérifie qu'il est fermé) : {e}")

    return {
        "status": "success",
        "message": f"{resultats['succes']} CV traités individuellement avec succès. ({resultats['erreurs']} échecs)"
    }

@app.get("/api/public/cv/download-excel")
async def download_excel_public():
    if os.path.exists(EXCEL_PATH):
        return FileResponse(
            EXCEL_PATH, 
            filename="Rapport_Candidats_SONASID.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    raise HTTPException(404, "Fichier Excel introuvable.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)