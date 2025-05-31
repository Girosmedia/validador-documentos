from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv() # Carga las variables de entorno del archivo .env

# Importamos nuestro orquestador de LangChain
from langchain_orchestrator import main_validation_chain_processor 

app = FastAPI()

# 1. Define el modelo para los datos del cliente
class ClientData(BaseModel):
    solicitud_id: str = Field(..., description="ID solicitud del cliente")
    solicitud_fecha_curse: Optional[str] = Field(None, description="Fecha de curse de la solicitud")
    cliente_nombres: str = Field(..., description="Nombres del cliente")
    cliente_apellido_paterno: Optional[str] = Field(None, description="Apellido paterno del cliente")
    cliente_apellido_materno: Optional[str] = Field(None, description="Apellido materno del cliente")
    cliente_rut: Optional[str] = Field(None, description="RUT del cliente (opcional)")

# 2. Define el modelo para un solo documento
class Document(BaseModel):
    filename: str = Field(..., description="Nombre del archivo del documento")
    tipo: str = Field(..., description="Tipo de documento (ej. 'CEDULA_IDENTIDAD', 'LIQUIDACION_SUELDO')")
    base64_content: str = Field(..., description="Contenido del documento en formato Base64")
    content_type: str = Field(..., description="Tipo de contenido del documento (ej. 'application/pdf')")

# 3. Define el modelo principal que encapsula todo el JSON
class CreditDocumentRequest(BaseModel):
    data_cliente: ClientData = Field(..., description="Todos los datos del cliente")
    data_documents: List[Document] = Field(..., description="Lista de documentos con su nombre y Base64")

@app.post("/validate_credit_documents_base64/")
async def validate_credit_documents_base64(
    request_data: CreditDocumentRequest # FastAPI automáticamente espera un JSON que coincida con este modelo
):
    print("🔍 Validando documentos de crédito en Base64...")
    client_data = request_data.data_cliente
    documents = request_data.data_documents

    print(f"Datos del cliente: {client_data.model_dump()}")

    for doc in documents:
        print(f"  - Documento: {doc.filename}, Tipo: {doc.content_type}, Tamaño Base64: {len(doc.base64_content)} caracteres")

    try:
        # 3. Invocar al orquestador LangChain con el payload de documentos Base64 y los datos del cliente
        print("\n--- Invocando al Orquestador LangChain ---")
        validation_results = await main_validation_chain_processor(
            documents_base64_payload=documents, # ¡Ahora pasamos el payload Base64!
            client_data=client_data.model_dump() 
        )
        
        print("--- Orquestador LangChain Finalizado ---")
        return JSONResponse(content=validation_results)

    except Exception as e:
        print(f"Error en el endpoint validate_credit_documents_base64: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor durante el procesamiento: {str(e)}")

# Endpoint de salud para verificar que la API está funcionando
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "API de validación de documentos en funcionamiento."}
