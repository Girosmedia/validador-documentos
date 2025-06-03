# agents/classification.py
from typing import Dict, Any
import os # Solo si necesitas acceder a variables de entorno para la API Key
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

google_api_key = os.getenv("GOOGLE_API_KEY") 

if not google_api_key:
    raise ValueError("La variable de entorno GOOGLE_API_KEY no está configurada para el agente de clasificación.")

GEMINI_CLASSIFICATION_MODEL = os.getenv("MODEL_LLM")

ollama_llm_classifier = ChatGoogleGenerativeAI(
    model=GEMINI_CLASSIFICATION_MODEL, 
    google_api_key=google_api_key, 
    temperature=0.1 # Temperatura baja para respuestas determinísticas
)

async def classify_document_chain(raw_text: str) -> Dict[str, Any]:
    doc_type = "OTRO" # Valor por defecto si no se clasifica
    classification_status = "failed"
    classification_error = None

    print(f"    🔎 Clasificando documento por texto extraído. Longitud: {len(raw_text)} caracteres.")

    try:
        prompt_text = f"""
        Eres un asistente experto en la clasificación de documentos chilenos.
        Tu tarea es identificar el tipo de documento basándote en el texto proporcionado.

        Los tipos de documentos posibles son:
        - CEDULA_IDENTIDAD (Cédula de Identidad)
        - LIQUIDACION_SUELDO (Liquidación de Sueldo)
        - COMPROBANTE_DOMICILIO (Comprobante de Domicilio, ej. boleta de servicios, certificado de residencia)
        - CERTIFICADO_DEUDA (Certificado de No Deuda de Alimentos u otros certificados de deuda)
        - REFERENCIAS_PERSONALES (Documentos con listas de contactos o referencias)
        - OTRO (si no encaja en ninguna de las categorías anteriores o el texto es insuficiente)

        Responde ÚNICAMENTE con la palabra clave que mejor represente el tipo de documento, sin añadir explicaciones ni ningún otro texto.
        Por ejemplo: "CEDULA_IDENTIDAD" o "COMPROBANTE_DOMICILIO".
        Si no puedes clasificarlo con certeza, responde "OTRO".

        Texto del documento:
        ---
        {raw_text}
        ---
        Tipo de documento:
        """
        
        response = await ollama_llm_classifier.ainvoke([HumanMessage(content=prompt_text)])
        

        predicted_type = response.content.strip().upper()


        allowed_types = ["CEDULA_IDENTIDAD", "LIQUIDACION_SUELDO", "COMPROBANTE_DOMICILIO", 
                         "CERTIFICADO_DEUDA", "REFERENCIAS_PERSONALES", "OTRO"]

        if predicted_type in allowed_types:
            doc_type = predicted_type
            classification_status = "classified"
        else:
            # Fallback si el LLM devuelve algo inesperado o no está en la lista
            doc_type = "OTRO" 
            classification_status = "failed"
            classification_error = f"El LLM devolvió un tipo inesperado: '{predicted_type}'. Clasificado como OTRO por defecto."
            print(f"    ⚠️ Fallo en clasificación: {classification_error}")

    except Exception as e:
        classification_error = f"Error al clasificar documento: {str(e)}"
        print(f"    🛑 ERROR en clasificación: {classification_error}")

    return {
        "doc_type": doc_type,
        "classification_status": classification_status,
        "classification_error": classification_error
    }