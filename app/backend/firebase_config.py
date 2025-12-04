import os
import firebase_admin
from firebase_admin import credentials, firestore

# Construir ruta absoluta al JSON
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(BASE_DIR, "firebaseKey.json")

# Inicializar Firebase con Firestore
cred = credentials.Certificate(KEY_PATH)

# Evitar doble inicialización si el script se importa varias veces
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Cliente Firestore REAL
db = firestore.client()
