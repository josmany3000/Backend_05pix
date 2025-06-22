# app.py

import os
import requests
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google.cloud import storage
from werkzeug.utils import secure_filename

# Cargar las variables de entorno desde un archivo .env (para desarrollo local)
load_dotenv()

# --- Configuración de Google Cloud Storage ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_CREDENTIALS_JSON_STR = os.getenv('GCS_CREDENTIALS_JSON')
storage_client = None

# Inicializar el cliente de GCS si las credenciales están disponibles
if GCS_CREDENTIALS_JSON_STR:
    try:
        import json
        gcs_credentials_dict = json.loads(GCS_CREDENTIALS_JSON_STR)
        storage_client = storage.Client.from_service_account_info(gcs_credentials_dict)
        print("Cliente de Google Cloud Storage inicializado correctamente.")
    except Exception as e:
        print(f"Error al inicializar el cliente de GCS. Asegúrate de que GCS_CREDENTIALS_JSON sea un JSON válido. Error: {e}")
else:
    print("Advertencia: Las credenciales de GCS (GCS_CREDENTIALS_JSON) no están configuradas.")

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

# --- Endpoint de Pixabay (ACTUALIZADO PARA ACEPTAR ORIENTACIÓN) ---
@app.route('/api/search-pixabay', methods=['GET'])
def search_pixabay():
    """
    Busca imágenes en la API de Pixabay.
    Ahora acepta 'orientation' y limita el largo del 'query'.
    """
    # 1. Obtener los parámetros de la URL
    query = request.args.get('q')
    orientation = request.args.get('orientation', 'all').lower()

    # 2. Validaciones de entrada
    if not query:
        return jsonify({"error": "Falta el parámetro de búsqueda 'q'"}), 400

    if orientation not in ['all', 'horizontal', 'vertical']:
        orientation = 'all' # Valor por defecto si no es válido

    if not PIXABAY_API_KEY:
        print("Error: PIXABAY_API_KEY no está configurada.")
        return jsonify({"error": "El servicio de búsqueda de imágenes no está configurado."}), 500
    
    # 3. Limitar la longitud del query a 100 caracteres (límite de Pixabay)
    if len(query) > 100:
        print(f"Advertencia: Query truncado a 100 caracteres. Original: {query}")
        query = query[:100]

    # 4. Preparar los parámetros para la petición a la API
    params = {
        'key': PIXABAY_API_KEY,
        'q': query,
        'image_type': 'photo',
        'lang': 'es',
        'per_page': 50,  # Aumentamos para tener más variedad de donde escoger
        'orientation': orientation # Parámetro de orientación añadido
    }

    # 5. Realizar la petición
    try:
        response = requests.get(PIXABAY_API_URL, params=params)
        response.raise_for_status() 
        data = response.json()
        return jsonify(data), 200
    except requests.exceptions.RequestException as e:
        print(f"Error al contactar la API de Pixabay: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio externo de imágenes."}), 502

# --- Endpoint para subir archivos a Google Cloud Storage ---
@app.route('/api/upload-media', methods=['POST'])
def upload_media():
    """
    Recibe un archivo (imagen/video) del frontend, lo sube a GCS y 
    devuelve una URL pública.
    """
    if not storage_client or not GCS_BUCKET_NAME:
        return jsonify({"error": "El servicio de almacenamiento no está configurado en el servidor."}), 500

    if 'file' not in request.files:
        return jsonify({"error": "No se encontró ninguna parte de archivo en la solicitud."}), 400
    
    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No se seleccionó ningún archivo."}), 400

    if file:
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}-{original_filename}"
        
        try:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(unique_filename)
            blob.upload_from_file(file, content_type=file.content_type)
            blob.make_public()
            return jsonify({"imageUrl": blob.public_url}), 200
        except Exception as e:
            print(f"Error al subir el archivo a GCS: {e}")
            return jsonify({"error": "No se pudo subir el archivo al almacenamiento en la nube."}), 500
    
    return jsonify({"error": "Ocurrió un error inesperado con el archivo."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))
        
