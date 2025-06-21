# app.py

import os
import requests
import uuid # NUEVO: Para generar nombres de archivo únicos
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google.cloud import storage # NUEVO: Importación de la librería de Google Cloud Storage
from werkzeug.utils import secure_filename # NUEVO: Para sanitizar nombres de archivo

# Cargar las variables de entorno desde un archivo .env (para desarrollo local)
load_dotenv()

# --- NUEVO: Configuración de Google Cloud Storage ---
# Estas variables se deben configurar en el entorno de Render
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_CREDENTIALS_JSON = os.getenv('GCS_CREDENTIALS_JSON')
storage_client = None

# Inicializar el cliente de GCS si las credenciales están disponibles
if GCS_CREDENTIALS_JSON:
    try:
        # Crea un cliente a partir del contenido del JSON en la variable de entorno
        storage_client = storage.Client.from_service_account_info(eval(GCS_CREDENTIALS_JSON))
        print("Cliente de Google Cloud Storage inicializado correctamente.")
    except Exception as e:
        print(f"Error al inicializar el cliente de GCS: {e}")
else:
    print("Advertencia: Las credenciales de GCS no están configuradas.")
# ----------------------------------------------------

# Inicializar la aplicación Flask
app = Flask(__name__)
CORS(app) 

# Configuración de Pixabay
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')
PIXABAY_API_URL = "https://pixabay.com/api/"

@app.route('/')
def home():
    """Ruta de bienvenida para verificar que el backend está funcionando."""
    return "Backend de Pixabay y GCS para Videos IA está activo."

# --- Endpoint de Pixabay (sin cambios) ---
@app.route('/api/search-pixabay', methods=['GET'])
def search_pixabay():
    # ... (código existente sin cambios)
    pass


# --- NUEVO: Endpoint para subir archivos a Google Cloud Storage ---
@app.route('/api/upload-media', methods=['POST'])
def upload_media():
    """
    Recibe un archivo (imagen/video) del frontend, lo sube a GCS y 
    devuelve una URL pública.
    """
    # Validar que el cliente de GCS y el nombre del bucket estén configurados
    if not storage_client or not GCS_BUCKET_NAME:
        return jsonify({"error": "El servicio de almacenamiento no está configurado en el servidor."}), 500

    # Validar que se haya enviado un archivo en la petición
    if 'file' not in request.files:
        return jsonify({"error": "No se encontró ninguna parte de archivo en la solicitud."}), 400
    
    file = request.files['file']

    # Validar que el archivo tenga un nombre
    if file.filename == '':
        return jsonify({"error": "No se seleccionó ningún archivo."}), 400

    if file:
        # Sanitizar el nombre del archivo original para seguridad
        original_filename = secure_filename(file.filename)
        # Crear un nombre de archivo único para evitar sobreescrituras
        unique_filename = f"{uuid.uuid4()}-{original_filename}"
        
        try:
            # Obtener el bucket de GCS
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            # Crear un "blob" (el objeto que representa el archivo en GCS)
            blob = bucket.blob(unique_filename)

            # Subir el archivo desde el stream de la petición
            blob.upload_from_file(
                file,
                content_type=file.content_type
            )
            
            # Hacer el archivo públicamente accesible
            blob.make_public()

            # Devolver la URL pública del archivo al frontend
            return jsonify({"imageUrl": blob.public_url}), 200

        except Exception as e:
            print(f"Error al subir el archivo a GCS: {e}")
            return jsonify({"error": "No se pudo subir el archivo al almacenamiento en la nube."}), 500
    
    return jsonify({"error": "Ocurrió un error inesperado con el archivo."}), 500
# ------------------------------------------------------------------


if __name__ == '__main__':
    app.run(port=5001, debug=True)
