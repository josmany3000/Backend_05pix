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
GCS_CREDENTIALS_JSON_STR = os.getenv('GCS_CREDENTIALS_JSON') # Renombrada para claridad
storage_client = None

# Inicializar el cliente de GCS si las credenciales están disponibles
if GCS_CREDENTIALS_JSON_STR:
    try:
        # Importante: Las credenciales en JSON deben ser parseadas correctamente.
        # En muchos entornos, el JSON se pasa como una cadena de texto.
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

# --- Endpoint de Pixabay (AHORA CORREGIDO Y COMPLETO) ---
@app.route('/api/search-pixabay', methods=['GET'])
def search_pixabay():
    """
    Busca imágenes en la API de Pixabay y devuelve los resultados.
    Esta función ahora maneja todos los casos y siempre devuelve una respuesta.
    """
    # 1. Obtener el término de búsqueda de los parámetros de la URL (?q=...)
    query = request.args.get('q')

    # 2. Validar que se haya proporcionado un término de búsqueda
    if not query:
        return jsonify({"error": "Falta el parámetro de búsqueda 'q'"}), 400

    # 3. Validar que la API Key de Pixabay esté configurada en el servidor
    if not PIXABAY_API_KEY:
        print("Error: PIXABAY_API_KEY no está configurada en las variables de entorno.")
        return jsonify({"error": "El servicio de búsqueda de imágenes no está configurado en el servidor."}), 500

    # 4. Preparar los parámetros para la petición a la API de Pixabay
    params = {
        'key': PIXABAY_API_KEY,
        'q': query,
        'image_type': 'photo',
        'lang': 'es',  # Buscar en español para mejores resultados locales
        'per_page': 20 # Limitar a 20 resultados
    }

    # 5. Realizar la petición y manejar posibles errores de conexión
    try:
        response = requests.get(PIXABAY_API_URL, params=params)
        # Si la respuesta de la API fue un error (ej: 4xx, 5xx), lanzar una excepción
        response.raise_for_status() 

        # Extraer los datos JSON de la respuesta
        data = response.json()
        
        # Devolver los datos al frontend. ¡Esta es una respuesta válida!
        return jsonify(data), 200

    except requests.exceptions.RequestException as e:
        # Este bloque se ejecuta si hay un problema de red o si la API de Pixabay devuelve un error.
        print(f"Error al contactar la API de Pixabay: {e}")
        return jsonify({"error": "No se pudo comunicar con el servicio externo de imágenes."}), 502 # 502 Bad Gateway es apropiado aquí


# --- Endpoint para subir archivos a Google Cloud Storage ---
@app.route('/api/upload-media', methods=['POST'])
def upload_media():
    """
    Recibe un archivo (imagen/video) del frontend, lo sube a GCS y 
    devuelve una URL pública.
    """
    # Validar que el cliente de GCS y el nombre del bucket estén configurados
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

            blob.upload_from_file(
                file,
                content_type=file.content_type
            )
            
            blob.make_public()

            return jsonify({"imageUrl": blob.public_url}), 200

        except Exception as e:
            print(f"Error al subir el archivo a GCS: {e}")
            return jsonify({"error": "No se pudo subir el archivo al almacenamiento en la nube."}), 500
    
    # Esta línea es un seguro, aunque es difícil llegar a ella con las validaciones anteriores.
    return jsonify({"error": "Ocurrió un error inesperado con el archivo."}), 500


if __name__ == '__main__':
    # El modo debug es útil para desarrollo, pero debe estar desactivado en producción.
    # Render lo maneja automáticamente.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))

