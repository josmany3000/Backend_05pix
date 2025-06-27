# app.py

import os
import requests
import uuid
import json
import time
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google.cloud import storage
from werkzeug.utils import secure_filename
import google.generativeai as genai

# Cargar las variables de entorno desde un archivo .env
load_dotenv()

# --- Configuración de Google Cloud Storage ---
GCS_BUCKET_NAME = os.getenv('GCS_BUCKET_NAME')
GCS_CREDENTIALS_JSON_STR = os.getenv('GCS_CREDENTIALS_JSON')
storage_client = None

if GCS_CREDENTIALS_JSON_STR:
    try:
        gcs_credentials_dict = json.loads(GCS_CREDENTIALS_JSON_STR)
        storage_client = storage.Client.from_service_account_info(gcs_credentials_dict)
        print("Cliente de Google Cloud Storage inicializado correctamente.")
    except Exception as e:
        print(f"Error al inicializar el cliente de GCS: {e}")
else:
    print("Advertencia: Las credenciales de GCS (GCS_CREDENTIALS_JSON) no están configuradas.")

# --- Configuración de Google Gemini ---
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        print("Cliente de Google Gemini inicializado correctamente.")
    except Exception as e:
        print(f"Error al configurar el cliente de Gemini: {e}")
else:
    print("Advertencia: La API Key de Google (GOOGLE_API_KEY) no está configurada. La generación de palabras clave estará deshabilitada.")

# --- Configuración de Pixabay ---
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')
PIXABAY_API_URL = "https://pixabay.com/api/"
PIXABAY_VIDEO_API_URL = "https://pixabay.com/api/videos/"

# Inicializar la aplicación Flask
app = Flask(__name__)
CORS(app)

# --- NUEVA FUNCIÓN ASISTENTE CON REINTENTOS ---
def fetch_from_pixabay_with_retry(url, params, max_retries=3, delay=1):
    """
    Realiza una petición a la API de Pixabay con reintentos en caso de error de conexión o servidor.
    Una respuesta válida con 0 resultados no activa un reintento.
    """
    for attempt in range(max_retries):
        try:
            # Se agrega un timeout para evitar que la petición se quede colgada indefinidamente
            response = requests.get(url, params=params, timeout=15)
            # Lanza una excepción para códigos de error HTTP (4xx o 5xx)
            response.raise_for_status()
            print(f"Éxito en intento {attempt + 1} para URL: {url} con query: '{params.get('q')}'")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Intento {attempt + 1}/{max_retries} falló para {url}. Error: {e}")
            if attempt < max_retries - 1:
                # Espera un momento antes de reintentar
                time.sleep(delay)
            else:
                print(f"Todos los {max_retries} reintentos fallaron para {url}.")
                return None # Devuelve None si todos los intentos fallan

def get_keywords_from_google_ai(script_text):
    """
    Usa la API de Google Gemini para extraer palabras clave de un guion.
    """
    if not GOOGLE_API_KEY:
        print("No se puede generar palabras clave: GOOGLE_API_KEY no está configurada.")
        return None

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Analiza el siguiente guion de una escena de video. Tu tarea es extraer de 4 a 5 palabras clave visuales y descriptivas que sirvan para buscar una imagen o video que represente la escena.

        Reglas importantes:
        1. Las palabras clave deben ser concisas y estar en español.
        2. La longitud total de todas las palabras clave juntas, separadas por espacios, no debe exceder los 100 caracteres.
        3. Responde únicamente con las palabras clave separadas por espacios. No incluyas numeración, viñetas, ni ninguna otra palabra como "Aquí están las palabras clave:".

        Ejemplo de guion: "El sol se pone lentamente sobre el océano, pintando el cielo con tonos naranjas y púrpuras. Las olas rompen suavemente en la orilla de arena blanca."
        Respuesta esperada para el ejemplo: "atardecer oceano olas playa arena"

        Guion para analizar:
        "{script_text}"
        """
        
        response = model.generate_content(prompt)
        keywords = response.text.strip().replace('\n', ' ').replace(',', ' ')
        
        if len(keywords) > 100:
            print(f"Advertencia: La IA generó keywords de más de 100 caracteres. Truncando: '{keywords}'")
            keywords = ' '.join(keywords[:100].split(' ')[:-1])

        print(f"Palabras clave generadas por IA: '{keywords}'")
        return keywords

    except Exception as e:
        print(f"Error al llamar a la API de Google Gemini: {e}")
        return None

@app.route('/')
def home():
    """Ruta de bienvenida para verificar que el backend está funcionando."""
    return "Backend de Pixabay y GCS para Videos IA está activo."

# --- ENDPOINT TOTALMENTE ACTUALIZADO ---
@app.route('/api/search-pixabay', methods=['GET'])
def search_pixabay_combined():
    """
    Recibe el guion, genera palabras clave con IA y busca tanto imágenes como videos en Pixabay.
    Combina los resultados y los devuelve en una sola respuesta.
    """
    # 1. Obtener los parámetros de la URL
    scene_script = request.args.get('q')
    orientation = request.args.get('orientation', 'all').lower()

    # 2. Validaciones de entrada
    if not scene_script:
        return jsonify({"error": "Falta el parámetro de guion 'q'"}), 400

    if orientation not in ['all', 'horizontal', 'vertical']:
        orientation = 'all'

    if not PIXABAY_API_KEY:
        print("Error: PIXABAY_API_KEY no está configurada.")
        return jsonify({"error": "El servicio de búsqueda de medios no está configurado."}), 500
    
    # 3. Generar palabras clave usando Google AI
    print(f"Recibido guion para procesar: '{scene_script[:150]}...'")
    search_query = get_keywords_from_google_ai(scene_script)

    # 4. Fallback: Si la IA falla, usar el guion original
    if not search_query:
        print("Fallback: Usando el guion original truncado porque la IA falló o está deshabilitada.")
        search_query = scene_script[:100]

    # 5. Preparar parámetros para las peticiones a Pixabay
    # Se piden 25 de cada uno para tener una buena mezcla
    image_params = {
        'key': PIXABAY_API_KEY, 'q': search_query, 'image_type': 'photo',
        'lang': 'es', 'per_page': 25, 'orientation': orientation
    }
    video_params = {
        'key': PIXABAY_API_KEY, 'q': search_query,
        'lang': 'es', 'per_page': 25, 'orientation': orientation
    }

    # 6. Realizar las peticiones con reintentos
    print("Buscando imágenes...")
    image_data = fetch_from_pixabay_with_retry(PIXABAY_API_URL, image_params)
    
    print("Buscando videos...")
    video_data = fetch_from_pixabay_with_retry(PIXABAY_VIDEO_API_URL, video_params)

    if image_data is None and video_data is None:
        return jsonify({"error": "El servicio externo de búsqueda de medios no responde."}), 502

    # 7. Combinar y normalizar los resultados
    all_hits = []

    # Procesar imágenes
    if image_data and image_data.get('hits'):
        for hit in image_data['hits']:
            hit['media_type'] = 'image' # Añadir tipo de medio
        all_hits.extend(image_data['hits'])

    # Procesar y normalizar videos
    if video_data and video_data.get('hits'):
        for hit in video_data['hits']:
            # Normalizar la estructura del video para que coincida con la de la imagen
            hit['media_type'] = 'video'
            video_info = hit.get('videos', {}).get('medium', {}) # Usar calidad media
            hit['webformatURL'] = video_info.get('url')
            # Construir una URL de previsualización consistente
            hit['previewURL'] = f"https://i.vimeocdn.com/video/{hit.get('picture_id')}_295x166.jpg"
            # Asegurarse de que campos comunes existan
            if 'tags' not in hit: hit['tags'] = ""
            if 'user' not in hit: hit['user'] = "Unknown"
        all_hits.extend(video_data['hits'])
    
    # 8. Mezclar aleatoriamente los resultados para una mejor presentación
    random.shuffle(all_hits)

    print(f"Búsqueda combinada exitosa. Se encontraron {len(all_hits)} resultados en total para '{search_query}'.")
    return jsonify({"totalHits": len(all_hits), "hits": all_hits}), 200


# --- Endpoint para subir archivos a Google Cloud Storage (sin cambios) ---
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
        # Crear un nombre de archivo único para evitar sobreescrituras
        unique_filename = f"{uuid.uuid4()}-{original_filename}"
        
        try:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(unique_filename)
            
            # Subir el archivo
            blob.upload_from_file(file, content_type=file.content_type)
            
            # Hacer el archivo público
            blob.make_public()
            
            print(f"Archivo '{unique_filename}' subido exitosamente a GCS.")
            return jsonify({"imageUrl": blob.public_url}), 200
        except Exception as e:
            print(f"Error al subir el archivo a GCS: {e}")
            return jsonify({"error": "No se pudo subir el archivo al almacenamiento en la nube."}), 500
    
    return jsonify({"error": "Ocurrió un error inesperado con el archivo."}), 500

if __name__ == '__main__':
    # El puerto se obtiene de las variables de entorno, ideal para despliegues en la nube
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))

