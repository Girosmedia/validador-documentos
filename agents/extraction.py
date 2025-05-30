# agents/extraction.py
from typing import Dict, Any
import os
import json # Para parsear la salida JSON del LLM
import fitz # PyMuPDF para obtener imagen de PDFs
from PIL import Image # Pillow para manipulación de imagen
import io # Para manejo de bytes de imagen
import base64 # Para codificar a Base64 para el LLM

# LangChain imports para Google Generative AI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# Reutilizamos la API Key (idealmente de variable de entorno)
google_api_key = os.getenv("GOOGLE_API_KEY") 
if not google_api_key:
    # Puedes hardcodearla aquí también para pruebas, pero recuerda la advertencia.
    # google_api_key = "AIzaSyCSJnRNqbRSzSsbJjXHuHYFWV3g_aNLCv0" 
    raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada para el agente de extracción.")

# Configuración del LLM para la extracción (DEBE ser multimodal)
GEMINI_EXTRACTION_MODEL = "gemini-1.5-flash" 

llm_extractor = ChatGoogleGenerativeAI(
    model=GEMINI_EXTRACTION_MODEL, 
    google_api_key=google_api_key, 
    temperature=0.3 # Temperatura baja para que sea determinístico en la extracción
)

# Reutilizamos la constante de redimensionamiento del preprocesamiento
MAX_IMAGE_DIMENSION = 900 # Mismo valor que en preprocessing.py

async def extract_credit_data_chain(filepath: str, doc_type: str) -> Dict[str, Any]:
    """
    Agente/Cadena de extracción de datos específicos.
    Utiliza un LLM multimodal (Gemini 1.5 Flash) para extraer campos clave según el tipo de documento.

    Args:
        filepath (str): Ruta del archivo original (usado para obtener la imagen).
        doc_type (str): El tipo de documento clasificado (ej., "CEDULA_IDENTIDAD").

    Returns:
        Dict[str, Any]: Diccionario con los datos extraídos y el estado.
    """
    extracted_data = {}
    extraction_status = "failed"
    extraction_error = None

    print(f"    ⚙️ Extrayendo datos para tipo: {doc_type} de {filepath}")

    try:
        # --- Prepara la imagen para el LLM multimodal (similar a preprocessing.py) ---
        images_for_llm_payload = [] 
        file_extension = os.path.splitext(filepath)[1].lower()

        if file_extension == ".pdf":
            with fitz.open(filepath) as doc:
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    pix = page.get_pixmap() 
                    img_bytes_raw = pix.pil_tobytes(format="PNG")
                    img_to_process = Image.open(io.BytesIO(img_bytes_raw))

                    width, height = img_to_process.size
                    if max(width, height) > MAX_IMAGE_DIMENSION:
                        ratio = MAX_IMAGE_DIMENSION / max(width, height)
                        new_width = int(width * ratio)
                        new_height = int(height * ratio)
                        img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
                    
                    output_buffer = io.BytesIO()
                    img_to_process.save(output_buffer, format="PNG")
                    images_for_llm_payload.append(output_buffer.getvalue()) 
        
        elif file_extension in [".jpg", ".jpeg", ".png"]:
            with open(filepath, "rb") as image_file:
                img_bytes_raw = image_file.read()
            
            img_to_process = Image.open(io.BytesIO(img_bytes_raw))
            
            width, height = img_to_process.size
            if max(width, height) > MAX_IMAGE_DIMENSION:
                ratio = MAX_IMAGE_DIMENSION / max(width, height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img_to_process = img_to_process.resize((new_width, new_height), Image.LANCZOS)
            
            output_buffer = io.BytesIO()
            img_to_process.save(output_buffer, format="PNG")
            images_for_llm_payload.append(output_buffer.getvalue()) 
        else:
            extraction_error = "Formato de archivo no soportado para extracción de datos visual."
            print(f"    ⚠️ {extraction_error}")
            return {
                "extracted_data": {},
                "extraction_status": "failed",
                "extraction_error": extraction_error
            }

        if not images_for_llm_payload:
            extraction_error = "No se pudo preparar ninguna imagen del documento para la extracción."
            print(f"    ⚠️ {extraction_error}")
            return {
                "extracted_data": {},
                "extraction_status": "failed",
                "extraction_error": extraction_error
            }


        # --- Prompts de extracción específicos por tipo de documento ---
        prompt_text = ""
        
        if doc_type == "CEDULA_IDENTIDAD":
            prompt_text = """
            Eres un asistente experto en la extracción de información de cédulas de identidad chilenas.
            Dada la imagen de una cédula de identidad chilena, extrae la siguiente información en formato JSON.
            Asegúrate de que la fecha de nacimiento, emisión y vencimiento estén en formato ISO 8601 (YYYY-MM-DD).
            El RUN debe incluir puntos y guion.
            
            JSON esperado:
            ```json
            {
                "nombre_completo": "Nombre completo del titular",
                "apellido_paterno": "Primer apellido del titular",
                "apellido_materno": "Segundo apellido del titular",
                "run": "RUN del titular (ej. 12.345.678-9)",
                "nacionalidad": "Nacionalidad (ej. CHILENA)",
                "sexo": "Sexo (M o F)",
                "fecha_nacimiento": "YYYY-MM-DD",
                "numero_documento": "Número de documento (9 dígitos, sin puntos ni guiones, si es posible)",
                "fecha_emision": "YYYY-MM-DD",
                "fecha_vencimiento": "YYYY-MM-DD",
                "lugar_nacimiento": "Lugar de nacimiento"
            }
            ```
            Si un campo no se encuentra en la imagen o no es claro, déjalo como `null`.
            IMPORTANTE: Responde ÚNICAMENTE con el objeto JSON. No añadas comentarios ni explicaciones.
            """
        elif doc_type == "COMPROBANTE_DOMICILIO":
            prompt_text = """
            Eres un asistente experto en la extracción de información de comprobantes de domicilio chilenos (ej. boletas de servicios).
            Dada la imagen de un comprobante de domicilio, extrae la siguiente información en formato JSON.
            
            JSON esperado:
            ```json
            {
                "nombre_titular": "Nombre completo del titular del servicio/cuenta",
                "direccion_completa": "Dirección completa (calle, número, depto/casa, comuna, ciudad, región)",
                "empresa_emisora": "Nombre de la empresa que emite el comprobante (ej. VTR, CGE, Aguas Andinas)",
                "numero_cliente_cuenta": "Número de cliente o cuenta del servicio",
                "fecha_emision": "Fecha de emisión del comprobante (YYYY-MM-DD)",
                "fecha_vencimiento": "Fecha de emisión del comprobante (YYYY-MM-DD)",
                "monto_total_pagar": "Monto total a pagar (solo número)",
                "periodo_facturado": "Periodo de facturación (ej. Enero 2025)"
            }
            ```
            Si un campo no se encuentra en la imagen o no es claro, déjalo como `null`.
            IMPORTANTE:Responde ÚNICAMENTE con el objeto JSON. No añadas comentarios ni explicaciones.
            RECUERDA: EL FORMATO DE FECHAS DEBE SER YYYY-MM-DD ASEGURATE DE RESPETARLO AL EXTRAER.
            
            """
        elif doc_type == "CERTIFICADO_DEUDA":
            prompt_text = """
            Eres un asistente experto en la extracción de información de certificados de deuda chilenos.
            Dada la imagen de un certificado de deuda, extrae la siguiente información en formato JSON.
            
            JSON esperado:
            ```json
            {
                "nombre_titular": "Nombre completo del titular del certificado",
                "run_titular": "RUN del titular (ej. 12.345.678-9)",
                "tipo_certificado": "Tipo específico de certificado (ej. Certificado de No Deuda de Alimentos)",
                "estado_deuda": "Estado de la deuda (ej. Sin inscripción vigente, Con deuda)",
                "fecha_emision": "Fecha de emisión del certificado (YYYY-MM-DD)",
                "codigo_verificacion": "Código de verificación del certificado"
            }
            ```
            Si un campo no se encuentra en la imagen o no es claro, déjalo como `null`.
            IMPORTANTE:Responde ÚNICAMENTE con el objeto JSON. No añadas comentarios ni explicaciones.
            """
        elif doc_type == "REFERENCIAS_PERSONALES":
             prompt_text = """
            Eres un asistente experto en la extracción de información de documentos de referencias personales.
            Dada la imagen de un documento con referencias personales, extrae la siguiente información en formato JSON.
            Debe ser una lista de objetos, donde cada objeto representa una referencia.
            
            JSON esperado:
            ```json
            [
                {
                    "nombre_referencia": "Nombre completo de la persona de referencia",
                    "relacion": "Relación con el solicitante (ej. HERMANA, MADRE, AMIGO, COLEGA)",
                    "numero_telefono": "Número de teléfono de la referencia (ej. +56912345678)"
                },
                {
                    "nombre_referencia": "...",
                    "relacion": "...",
                    "numero_telefono": "..."
                }
            ]
            ```
            Si un campo no se encuentra o no es claro, déjalo como `null`.
            IMPORTANTE:Responde ÚNICAMENTE con el array JSON. No añadas comentarios ni explicaciones.
            """
        else:
            print(f"    ⚠️ No hay prompt de extracción específico para el tipo de documento: {doc_type}. Intentando extracción general.")
            # Fallback para tipos de documento "OTRO" o no definidos, pidiendo texto plano.
            prompt_text = "Extrae todo el texto visible de este documento. Responde ÚNICAMENTE con el texto plano extraído."
            # No esperamos JSON en este caso
            
        # Construir el mensaje para el LLM multimodal
        message_content = [
            {"type": "text", "text": prompt_text},
        ]
        # Añadir las imágenes usando el formato "image_url" y Base64
        for img_bytes_data in images_for_llm_payload:
            img_b64_str = base64.b64encode(img_bytes_data).decode('utf-8')
            message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str}"}}) 

        prompt_parts = [
            HumanMessage(content=message_content) # Pasar la lista construida
        ]
        
        print(f"    🤖 Enviando imagen(es) al LLM para extracción de datos específicos...")
        llm_response = await llm_extractor.ainvoke(prompt_parts)
        
        raw_llm_output = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        
        # Intentar parsear la respuesta como JSON solo si esperamos un JSON
        if doc_type in ["CEDULA_IDENTIDAD", "COMPROBANTE_DOMICILIO", "CERTIFICADO_DEUDA", "REFERENCIAS_PERSONALES"]:
            try:
                # El LLM a veces puede encerrar el JSON en bloques de código markdown, hay que limpiarlo
                if raw_llm_output.strip().startswith("```json") and raw_llm_output.strip().endswith("```"):
                    json_str = raw_llm_output.strip()[len("```json"): -len("```")].strip()
                else:
                    json_str = raw_llm_output.strip()
                
                extracted_data = json.loads(json_str)
                extraction_status = "extracted"
                print("    ✅ Datos extraídos en formato JSON.")
            except json.JSONDecodeError as e:
                extraction_error = f"La respuesta del LLM no es un JSON válido: {e}. Respuesta: {raw_llm_output[:500]}..."
                print(f"    ⚠️ {extraction_error}")
                extracted_data = {"raw_llm_output": raw_llm_output} # Para depuración
                extraction_status = "failed_json_parse"
        else: # Para tipos "OTRO" o no definidos, simplemente devolvemos el texto plano
            extracted_data = {"text_content": raw_llm_output}
            extraction_status = "extracted_raw_text"
            print("    ✅ Texto extraído (no JSON, ya que no hay prompt específico).")


    except Exception as e:
        extraction_error = f"Error general al extraer datos para '{doc_type}': {str(e)}"
        print(f"    🛑 ERROR en extracción: {extraction_error}")
            
    return {
        "extracted_data": extracted_data,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error
    }