from typing import List, Dict, Any
import os
import fitz # PyMuPDF
from PIL import Image # Pillow para PyMuPDF al convertir a imagen y redimensionar
import io # Para manejar datos binarios en memoria
import base64 # Para codificar/decodificar Base64
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

class DocumentBase64(BaseModel):
    filename: str
    base64_content: str
    content_type: str

# --- Configuración del LLM Multimodal (AHORA GEMINI) ---
# Modelo de Google Generative AI
GOOGLE_GENERATIVE_AI_MODEL = os.getenv("MODEL_LLM")

# Obtén tu API Key de Google AI Studio y guárdala como variable de entorno.
google_api_key = os.getenv("GOOGLE_API_KEY") 
if not google_api_key:
    raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada.")

print(f"🧠 Inicializando LLM de Google Generative AI: {GOOGLE_GENERATIVE_AI_MODEL}")

# Inicializa el cliente de Gemini
LLM = ChatGoogleGenerativeAI(
    model=GOOGLE_GENERATIVE_AI_MODEL, 
    google_api_key=google_api_key, 
    temperature=0.3
)

# --- Configuración de Redimensionamiento de Imagen ---
MAX_IMAGE_DIMENSION = 900

async def preprocess_documents_chain(documents_payload: List[DocumentBase64]) -> Dict[str, Any]:

    processed_results = {}

    for doc_obj in documents_payload:
        doc_id = doc_obj.filename # Usamos el nombre del archivo como ID
        base64_content = doc_obj.base64_content
        content_type = doc_obj.content_type
        
        extracted_content = ""
        status = "error"
        error_msg = None

        print(f"\n--- 📄 Procesando documento Base64: {doc_id} (Tipo: {content_type}) ---")

        try:
            # Decodificar el contenido Base64 a bytes binarios
            doc_bytes = base64.b64decode(base64_content)
            images_for_llm_payload = [] 
            
            # --- Lógica específica para PDFs ---
            if content_type == "application/pdf":
                pdf_text_extracted_digital = ""
                
                # Usar io.BytesIO para que fitz (PyMuPDF) pueda leer desde memoria
                with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
                    for page_num in range(doc.page_count):
                        page = doc[page_num]
                        
                        # 1. Intentar extraer texto digital primero
                        page_text = page.get_text()
                        if page_text.strip():
                            pdf_text_extracted_digital += page_text + "\n"
                            print(f"    📜 Página {page_num+1} (PDF digital): Texto extraído directamente.")
                        else:
                            # 2. Si no hay texto digital, preparar para LLM multimodal
                            print(f"    🖼️ Página {page_num+1} (PDF escaneado/imagen): Convirtiendo a imagen para LLM...")
                            pix = page.get_pixmap() 
                            img_bytes_raw = pix.pil_tobytes(format="PNG") # Convertir pixmap a bytes PNG

                            img_to_process = Image.open(io.BytesIO(img_bytes_raw))

                            # Redimensionar la imagen para el LLM
                            width, height = img_to_process.size
                            if max(width, height) > MAX_IMAGE_DIMENSION:
                                ratio = MAX_IMAGE_DIMENSION / max(width, height)
                                new_width = int(width * ratio)
                                new_height = int(height * ratio)
                                print(f"    📏 Redimensionando de {width}x{height} a {new_width}x{new_height}...")
                                img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
                            
                            output_buffer = io.BytesIO()
                            img_to_process.save(output_buffer, format="PNG")
                            images_for_llm_payload.append(output_buffer.getvalue()) # Añadir los bytes redimensionados

                # Consolidar el texto o invocar al LLM si es necesario
                if pdf_text_extracted_digital.strip():
                    extracted_content = pdf_text_extracted_digital
                    status = "processed_digital_pdf" 
                    print("    ✅ Contenido extraído del PDF digital.")
                elif images_for_llm_payload: # Si hay imágenes para el LLM (PDFs escaneados)
                    print(f"    🤖 Invocando LLM para {len(images_for_llm_payload)} imágenes de PDF escaneado...")
                    
                    message_content = [
                        {"type": "text", "text": "Extrae TODO el texto visible, palabra por palabra, caracter por caracter, de la siguiente imagen, sin omitir nada. Incluye texto de tablas, campos y cualquier sección del documento. No hagas resúmenes, no interpretes, no añadas comentarios ni explicaciones. Responde ÚNICAMENTE con el texto plano extraído."},
                    ]
                    for img_bytes_data in images_for_llm_payload:
                        img_b64_str_llm = base64.b64encode(img_bytes_data).decode('utf-8')
                        message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str_llm}"}}) 

                    prompt_parts = [HumanMessage(content=message_content)]
                    llm_response = await LLM.ainvoke(prompt_parts)
                    extracted_content = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)

                    if extracted_content.strip():
                        status = "processed_llm_ocr" 
                        print(f"    ✅ Texto extraído por LLM. Longitud: {len(extracted_content)} caracteres.")
                    else:
                        status = "no_text_found_by_llm"
                        error_msg = "El LLM no pudo extraer texto del PDF escaneado."
                        print(f"    ⚠️ {error_msg}")
                else: # PDF vacío o sin contenido detectable
                    status = "no_content"
                    error_msg = "El PDF no contiene texto digital ni imágenes procesables."
                    print(f"    ⚠️ {error_msg}")

            # --- Lógica para Imágenes Directas (JPG, PNG) ---
            elif content_type in ["image/jpeg", "image/png"]:
                print(f"    🖼️ Detectada imagen directa. Preparando para el LLM...")
                
                img_to_process = Image.open(io.BytesIO(doc_bytes)) # Abrir desde bytes
                
                # Redimensionar la imagen para el LLM
                width, height = img_to_process.size
                if max(width, height) > MAX_IMAGE_DIMENSION:
                    ratio = MAX_IMAGE_DIMENSION / max(width, height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    print(f"    📏 Redimensionando de {width}x{height} a {new_width}x{new_height}...")
                    img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
                
                output_buffer = io.BytesIO()
                img_to_process.save(output_buffer, format="PNG") # Guardar como PNG para LLM
                images_for_llm_payload.append(output_buffer.getvalue()) 

                print(f"    🤖 Invocando LLM para imagen directa...")
                
                message_content = [
                    {"type": "text", "text": "Extrae TODO el texto visible, palabra por palabra, caracter por caracter, de la siguiente imagen, sin omitir nada. Incluye texto de tablas, campos y cualquier sección del documento. No hagas resúmenes, no interpretes, no añadas comentarios ni explicaciones. Responde ÚNICAMENTE con el texto plano extraído."},
                ]
                img_b64_str_llm = base64.b64encode(images_for_llm_payload[0]).decode('utf-8')
                message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str_llm}"}}) 

                prompt_parts = [HumanMessage(content=message_content)]
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
                error_msg = f"Tipo de contenido no soportado para preprocesamiento: {content_type}"
                print(f"    ❌ {error_msg}")
            
            # Normalizar el texto (si se extrajo algo)
            if extracted_content:
                extracted_content = ' '.join(extracted_content.split()).strip()

        except Exception as e:
            status = "processing_failed"
            error_msg = f"Error general al preprocesar documento Base64 '{doc_id}': {str(e)}"
            print(f"    🛑 ERROR: {error_msg}")
            
        processed_results[doc_id] = {
            "filename": doc_id, # Usamos filename para identificar el documento
            "raw_text": extracted_content if extracted_content else None, 
            "status": status,
            "error_message": error_msg
        }
        print(f"  📊 Resultado final para {doc_id}: Status={status}, Error={error_msg or 'N/A'}")

    return processed_results