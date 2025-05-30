# agents/preprocessing.py
from typing import List, Dict, Any
import os
import fitz # PyMuPDF
from PIL import Image # Pillow para PyMuPDF al convertir a imagen y redimensionar
import io # Para manejar datos binarios en memoria
import base64 # Para codificar imágenes a Base64 para el LLM

# LangChain imports para Google Generative AI
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_core.messages import HumanMessage, SystemMessage

# --- Configuración del LLM Multimodal (AHORA GEMINI) ---
# Modelo de Google Generative AI
GOOGLE_GENERATIVE_AI_MODEL = "gemma-3-27b-it" 

# Obtén tu API Key de Google AI Studio y guárdala como variable de entorno.
# ¡ADVERTENCIA! No es seguro hardcodear la API Key directamente en el código de producción.
# Para producción, usa os.getenv("GOOGLE_API_KEY") y configura la variable de entorno.
# google_api_key = os.getenv("GOOGLE_API_KEY") 
# if not google_api_key:
#     raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada.")
google_api_key = os.getenv("GOOGLE_API_KEY")  # Para pruebas rápidas, pero cambiar en producción

print(f"🧠 Inicializando LLM de Google Generative AI: {GOOGLE_GENERATIVE_AI_MODEL}")

# Inicializa el cliente de Gemini
# temperature=0.1 para que las respuestas sean más determinísticas y menos creativas
LLM = ChatGoogleGenerativeAI(
    model=GOOGLE_GENERATIVE_AI_MODEL, 
    google_api_key=google_api_key, 
    temperature=0.3
)

# --- Configuración de Redimensionamiento de Imagen ---
# Define la dimensión máxima (ancho o alto) para las imágenes enviadas al LLM.
# Si una imagen excede esta dimensión, se redimensionará manteniendo su proporción.
# Prueba con 512. Si el error persiste, puedes bajarlo.
MAX_IMAGE_DIMENSION = 900

async def preprocess_documents_chain(document_paths: List[str]) -> Dict[str, Any]:
    """
    Agente/Cadena de preprocesamiento de documentos.
    Intenta extraer texto de PDFs digitales directamente. Si son PDFs escaneados o imágenes,
    usa un LLM multimodal de Gemini para la extracción, redimensionando las imágenes si es necesario.

    Args:
        document_paths (List[str]): Rutas absolutas a los documentos temporales.

    Returns:
        Dict[str, Any]: Diccionario con el texto extraído y metadatos por cada documento.
    """
    processed_results = {}

    for doc_path in document_paths:
        doc_id = os.path.basename(doc_path)
        extracted_content = ""
        status = "error"
        error_msg = None

        print(f"\n--- 📄 Procesando documento: {doc_path} ---")

        try:
            file_extension = os.path.splitext(doc_path)[1].lower()
            
            # Lista para almacenar los bytes de las imágenes para el LLM
            images_for_llm_payload = [] 
            
            # --- Lógica específica para PDFs ---
            if file_extension == ".pdf":
                pdf_text_extracted_digital = ""
                
                with fitz.open(doc_path) as doc:
                    for page_num in range(doc.page_count):
                        page = doc[page_num]
                        
                        # 1. Intentar extraer texto digital primero
                        page_text = page.get_text()
                        if page_text.strip():
                            pdf_text_extracted_digital += page_text + "\n"
                            print(f"    📜 Página {page_num+1} (PDF digital): Texto extraído directamente.")
                        else:
                            # 2. Si no hay texto digital, preparar para LLM multimodal
                            print(f"    🖼️ Página {page_num+1} (PDF escaneado/imagen): Convirtiendo a imagen para LLM...")
                            pix = page.get_pixmap() 
                            img_bytes_raw = pix.pil_tobytes(format="PNG")

                            img_to_process = Image.open(io.BytesIO(img_bytes_raw))

                            # Redimensionar la imagen para el LLM
                            width, height = img_to_process.size
                            if max(width, height) > MAX_IMAGE_DIMENSION:
                                ratio = MAX_IMAGE_DIMENSION / max(width, height)
                                new_width = int(width * ratio)
                                new_height = int(height * ratio)
                                print(f"    📏 Redimensionando de {width}x{height} a {new_width}x{new_height}...")
                                img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
                            
                            output_buffer = io.BytesIO()
                            img_to_process.save(output_buffer, format="PNG")
                            images_for_llm_payload.append(output_buffer.getvalue()) # Añadir los bytes
                            
                            # --- CÓDIGO DE DEPURACIÓN CRÍTICO: GUARDAR IMAGEN TEMPORAL ---
                            # Guarda la imagen original del pixmap para ver qué extrae PyMuPDF
                            debug_original_img_path = f"debug_original_page_{page_num+1}_{doc_id}.png"
                            with open(debug_original_img_path, "wb") as f:
                                f.write(img_bytes_raw)
                            print(f"    ⚠️ DEBUG: Imagen de página original guardada en {debug_original_img_path} para inspección.")
                            # --- FIN CÓDIGO DE DEPURACIÓN ---

                            # --- CÓDIGO DE DEPURACIÓN CRÍTICO: GUARDAR IMAGEN REDIMENSIONADA ---
                            # Guarda la imagen redimensionada antes de Base64
                            output_buffer_debug = io.BytesIO()
                            img_to_process.save(output_buffer_debug, format="PNG")
                            debug_resized_img_path = f"debug_resized_page_{page_num+1}_{doc_id}.png"
                            with open(debug_resized_img_path, "wb") as f:
                                f.write(output_buffer_debug.getvalue())
                            print(f"    ⚠️ DEBUG: Imagen de página redimensionada guardada en {debug_resized_img_path} para inspección.")
                            # --- FIN CÓDIGO DE DEPURACIÓN ---
                
                # Consolidar el texto o invocar al LLM si es necesario
                if pdf_text_extracted_digital.strip():
                    extracted_content = pdf_text_extracted_digital
                    status = "processed_digital_pdf" # Nuevo status para indicar origen
                    print("    ✅ Contenido extraído del PDF digital.")
                elif images_for_llm_payload: # Si hay imágenes para el LLM (PDFs escaneados)
                    print(f"    🤖 Invocando LLM para {len(images_for_llm_payload)} imágenes de PDF escaneado...")
                    
                    # --- CONSTRUCCIÓN DEL MENSAJE MULTIMODAL CORRECTA PARA GEMINI ---
                    message_content = [
                        {"type": "text", "text": "Extrae TODO el texto visible, palabra por palabra, caracter por caracter, de la siguiente imagen, sin omitir nada. Incluye texto de tablas, campos y cualquier sección del documento. No hagas resúmenes, no interpretes, no añadas comentarios ni explicaciones. Responde ÚNICAMENTE con el texto plano extraído."},
                    ]
                    # Añadir las imágenes usando el formato "image_url" y Base64
                    for img_bytes_data in images_for_llm_payload:
                        img_b64_str = base64.b64encode(img_bytes_data).decode('utf-8')
                        message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str}"}}) 

                    prompt_parts = [
                        # SystemMessage(
                        #     content="Eres un asistente experto en la extracción de texto de documentos."
                        # ),
                        HumanMessage(content=message_content) # Pasar la lista construida
                    ]
                    # --- FIN CONSTRUCCIÓN DEL MENSAJE ---

                    llm_response = await LLM.ainvoke(prompt_parts)
                    extracted_content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)

                    if extracted_content.strip():
                        status = "processed_llm_ocr" # Nuevo status para indicar LLM-OCR
                        print(f"    ✅ Texto extraído por LLM. Longitud: {len(extracted_content)} caracteres.")
                    else:
                        status = "no_text_found_by_llm"
                        error_msg = "El LLM no pudo extraer texto del PDF escaneado."
                        print(f"    ⚠️ {error_msg}")
                else: # PDF vacío o sin contenido detectable
                    status = "no_content"
                    error_msg = "El PDF no contiene texto digital ni imágenes procesables."
                    print(f"    ⚠️ {error_msg}")

            # --- Lógica para Imágenes Directas (JPG, PNG) ---
            elif file_extension in [".jpg", ".jpeg", ".png"]:
                print(f"    🖼️ Detectada imagen directa. Preparando para el LLM...")
                with open(doc_path, "rb") as image_file:
                    img_bytes_raw = image_file.read()
                
                img_to_process = Image.open(io.BytesIO(img_bytes_raw))
                
                # Redimensionar la imagen para el LLM
                width, height = img_to_process.size
                if max(width, height) > MAX_IMAGE_DIMENSION:
                    ratio = MAX_IMAGE_DIMENSION / max(width, height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    print(f"    📏 Redimensionando de {width}x{height} a {new_width}x{new_height}...")
                    img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
                
                output_buffer = io.BytesIO()
                img_to_process.save(output_buffer, format="PNG")
                images_for_llm_payload.append(output_buffer.getvalue()) # Añadir los bytes

                # --- CÓDIGO DE DEPURACIÓN CRÍTICO: GUARDAR IMAGEN TEMPORAL ---
                # Guarda la imagen original del pixmap para ver qué extrae PyMuPDF
                debug_original_img_path = f"debug_original_image_{doc_id}.png"
                with open(debug_original_img_path, "wb") as f:
                    f.write(img_bytes_raw)
                print(f"    ⚠️ DEBUG: Imagen original guardada en {debug_original_img_path} para inspección.")
                # --- FIN CÓDIGO DE DEPURACIÓN ---

                # --- CÓDIGO DE DEPURACIÓN CRÍTICO: GUARDAR IMAGEN REDIMENSIONADA ---
                # Guarda la imagen redimensionada antes de Base64
                output_buffer_debug = io.BytesIO()
                img_to_process.save(output_buffer_debug, format="PNG")
                debug_resized_img_path = f"debug_resized_image_{doc_id}.png"
                with open(debug_resized_img_path, "wb") as f:
                    f.write(output_buffer_debug.getvalue())
                print(f"    ⚠️ DEBUG: Imagen redimensionada guardada en {debug_resized_img_path} para inspección.")
                # --- FIN CÓDIGO DE DEPURACIÓN ---

                # LLAMADA AL LLM MULTIMODAL (GEMINI)
                print(f"    🤖 Invocando LLM para imagen directa...")
                
                # --- CONSTRUCCIÓN DEL MENSAJE MULTIMODAL CORRECTA PARA GEMINI ---
                message_content = [
                    {"type": "text", "text": "Extrae TODO el texto visible, palabra por palabra, caracter por caracter, de la siguiente imagen, sin omitir nada. Incluye texto de tablas, campos y cualquier sección del documento. No hagas resúmenes, no interpretes, no añadas comentarios ni explicaciones. Responde ÚNICAMENTE con el texto plano extraído."},
                ]
                # Para una sola imagen, codificamos y agregamos usando el formato "image_url"
                img_b64_str = base64.b64encode(images_for_llm_payload[0]).decode('utf-8')
                message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str}"}}) 

                prompt_parts = [
                    # SystemMessage(
                    #     content="Eres un asistente experto en la extracción de texto de documentos."
                    # ),
                    HumanMessage(content=message_content) # Pasar la lista construida
                ]
                # --- FIN CONSTRUCCIÓN DEL MENSAJE ---

                llm_response = await LLM.ainvoke(prompt_parts)
                extracted_content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)

                if extracted_content.strip():
                    status = "processed_llm_ocr"
                    print(f"    ✅ Texto extraído por LLM. Longitud: {len(extracted_content)} caracteres.")
                else:
                    status = "no_text_found_by_llm"
                    error_msg = "El LLM no pudo extraer texto de la imagen directa."
                    print(f"    ⚠️ {error_msg}")
            
            # --- Formato no soportado ---
            else:
                status = "unsupported_format"
                error_msg = f"Formato de archivo no soportado para preprocesamiento: {file_extension}"
                print(f"    ❌ {error_msg}")
            
            # Normalizar el texto (si se extrajo algo)
            if extracted_content:
                extracted_content = ' '.join(extracted_content.split()).strip()

        except Exception as e:
            status = "processing_failed"
            error_msg = f"Error general al procesar con LLM multimodal para '{doc_id}': {str(e)}"
            print(f"    🛑 ERROR: {error_msg}")
            
        processed_results[doc_id] = {
            "filepath": doc_path,
            "raw_text": extracted_content if extracted_content else None, # Guardar raw_text solo si no está vacío
            "status": status,
            "error_message": error_msg
        }
        print(f"  📊 Resultado final para {doc_id}: Status={status}, Error={error_msg or 'N/A'}")

    return processed_results