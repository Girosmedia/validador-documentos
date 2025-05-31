# agents/extraction.py
from typing import Dict, Any, Optional
import os
import json 
import fitz 
from PIL import Image 
import io 
import base64 

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

google_api_key = os.getenv("GOOGLE_API_KEY") 
if not google_api_key:
    raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada para el agente de extracción.")

GEMINI_EXTRACTION_MODEL = os.getenv("MODEL_LLM")

llm_extractor = ChatGoogleGenerativeAI(
    model=GEMINI_EXTRACTION_MODEL, 
    google_api_key=google_api_key, 
    temperature=0.1
)

MAX_IMAGE_DIMENSION = 900 # Mismo valor que en preprocessing.py

async def extract_credit_data_chain(
    raw_text: str, # Texto extraído del preprocesamiento
    doc_type: str,
    base64_content: str, # Nuevo: Contenido Base64 original
    content_type: str # Nuevo: Tipo de contenido original
) -> Dict[str, Any]:
    extracted_data = {}
    extraction_status = "failed"
    extraction_error = None

    print(f"    ⚙️ Extrayendo datos para tipo: {doc_type} desde Base64 (Tipo: {content_type})")

    try:
        # Decodificar el contenido Base64 a bytes binarios
        doc_bytes = base64.b64decode(base64_content)

        # --- Prepara la imagen para el LLM multimodal (similar a preprocessing.py) ---
        images_for_llm_payload = [] 
        
        if content_type == "application/pdf":
            with fitz.open(stream=doc_bytes, filetype="pdf") as doc:
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
            
        elif content_type in ["image/jpeg", "image/png"]:
            img_to_process = Image.open(io.BytesIO(doc_bytes))
            
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
            extraction_error = f"Tipo de contenido '{content_type}' no soportado para extracción de datos visual."
            print(f"    ⚠️ {extraction_error}")
            return {
                "extracted_data": {},
                "extraction_status": "failed",
                "extraction_error": extraction_error
            }

        if not images_for_llm_payload:
            extraction_error = "No se pudo preparar ninguna imagen del documento Base64 para la extracción."
            print(f"    ⚠️ {extraction_error}")
            return {
                "extracted_data": {},
                "extraction_status": "failed",
                "extraction_error": extraction_error
            }

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
                "nombres": "Solo Nombres del titular",
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
                "nombres": "Solo Nombres del titular",
                "apellido_paterno": "Primer apellido del titular",
                "apellido_materno": "Segundo apellido del titular",
                "direccion_completa": "Dirección completa (calle, número, depto/casa, comuna, ciudad, región)",
                "empresa_emisora": "Nombre de la empresa que emite el comprobante (ej. VTR, CGE, Aguas Andinas)",
                "numero_cliente_cuenta": "Número de cliente o cuenta del servicio",
                "fecha_emision": "Fecha de emisión del comprobante (YYYY-MM-DD)",
                "fecha_vencimiento": "Fecha de vencimiento del comprobante (YYYY-MM-DD)",
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
            EL ESTADO DE LA DEUDA DEBE SER INTERPRETADO COMO "CON ANOTACIONES" O "SIN ANOTACIONES" no agregues más estados.
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
        elif doc_type == "LIQUIDACION_SUELDO":
            prompt_text = """
            Eres un asistente experto en la extracción de información de liquidaciones de sueldo chilenas.
            Dada la imagen de una liquidación de sueldo, extrae la siguiente información en formato JSON.
            Los montos (sueldo_bruto, sueldo_liquido, descuentos, imposiciones) deben ser solo números.
            Las fechas deben ser YYYY-MM-DD.
            
            JSON esperado:
            ```json
            {
                "nombre_empleado": "Nombre completo del empleado",
                "run_empleado": "RUN del empleado (ej. 12.345.678-9)",
                "rut_empresa": "RUN de la empresa",
                "nombre_empresa": "Nombre de la empresa",
                "cargo": "Cargo del empleado",
                "periodo": "Periodo de liquidación (ej. Mayo 2025)",
                "fecha_emision": "YYYY-MM-DD",
                "sueldo_bruto": 1234567,
                "sueldo_liquido": 987654,
                "total_descuentos": 100000,
                "total_imposiciones": 50000,
                "tipo_contrato": "Tipo de contrato (ej. INDEFINIDO, PLAZO_FIJO)"
            }
            ```
            Si un campo no se encuentra en la imagen o no es claro, déjalo como `null`.
            IMPORTANTE: Responde ÚNICAMENTE con el objeto JSON. No añadas comentarios ni explicaciones.
            """
        else:
            print(f"    ⚠️ No hay prompt de extracción específico para el tipo de documento: {doc_type}. Intentando extracción general.")
            if raw_text:
                extracted_data = {"text_content": raw_text}
                extraction_status = "extracted_raw_text"
                print("    ✅ Texto ya extraído en preprocesamiento. No se requiere LLM para extracción específica.")
                return {
                    "extracted_data": extracted_data,
                    "extraction_status": extraction_status,
                    "extraction_error": None
                }
            else:
                extraction_error = "No hay texto pre-extraído y no hay prompt específico para extracción estructurada de este tipo de documento."
                print(f"    ❌ {extraction_error}")
                return {
                    "extracted_data": {},
                    "extraction_status": "failed",
                    "extraction_error": extraction_error
                }
            
        message_content = [
            {"type": "text", "text": prompt_text},
        ]
        # Añadir las imágenes usando el formato "image_url" y Base64
        for img_bytes_data in images_for_llm_payload:
            img_b64_str = base64.b64encode(img_bytes_data).decode('utf-8')
            message_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64_str}"}}) 

        prompt_parts = [
            HumanMessage(content=message_content) 
        ]
        
        print(f"    🤖 Enviando imagen(es) al LLM para extracción de datos específicos...")
        llm_response = await llm_extractor.ainvoke(prompt_parts)
        
        raw_llm_output = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        
        # Intentar parsear la respuesta como JSON
        try:
            # El LLM a veces puede encerrar el JSON en bloques de código markdown, hay que limpiarlo
            if raw_llm_output.strip().startswith("```json") and raw_llm_output.strip().endswith("```"):
                json_str = raw_llm_output.strip()[len("```json"): -len("```")].strip()
            else:
                json_str = raw_llm_output.strip()
            
            extracted_data = json.loads(json_str)
            extraction_status = "extracted"
            print("    ✅ Datos extraídos en formato JSON.")
        except json.JSONDecodeError as e:
            extraction_error = f"La respuesta del LLM no es un JSON válido para extracción: {e}. Respuesta: {raw_llm_output[:500]}..."
            print(f"    ⚠️ {extraction_error}")
            extracted_data = {"raw_llm_output": raw_llm_output} # Para depuración
            extraction_status = "failed_json_parse"


    except Exception as e:
        extraction_error = f"Error general al extraer datos para '{doc_type}': {str(e)}"
        print(f"    🛑 ERROR en extracción: {extraction_error}")
            
    return {
        "extracted_data": extracted_data,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error
    }