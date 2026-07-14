from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["sonasid_rh"]

# Test
db.test.insert_one({"ok": True})
print("✅ MongoDB connecté !")
print(f"Bases: {client.list_database_names()}")

# Nettoyer
db.test.drop()