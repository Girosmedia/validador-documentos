# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import List
import os
import shutil # Para mover archivos de forma segura

from dotenv import load_dotenv
load_dotenv()

# Importamos nuestro orquestador de LangChain (aún no implementado)
from langchain_orchestrator import main_validation_chain_processor 

app = FastAPI(
    title="API de Validación de Documentos de Crédito",
    description="API para recibir y validar automáticamente la documentación de créditos."
)

# Directorio temporal para almacenar los documentos recibidos
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True) # Crea el directorio si no existe

@app.post("/validate_credit_docs/")
async def validate_credit_documents(files: List[UploadFile] = File(...)):
    """
    Recibe uno o múltiples documentos de crédito para su validación.
    
    Args:
        files (List[UploadFile]): Lista de archivos (ej. PDF, JPG, PNG) a validar.
                                 FastAPI maneja la carga de archivos automáticamente.
                                 
    Returns:
        dict: Un diccionario con el estado de la validación y los resultados.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No se han proporcionado archivos.")

    document_paths = []
    try:
        for file in files:
            # Generar un nombre de archivo único para evitar colisiones
            file_location = os.path.join(UPLOAD_DIR, file.filename)
            
            # Guardar el archivo de forma asíncrona
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            document_paths.append(file_location)
            print(f"Archivo '{file.filename}' guardado en '{file_location}'")

        # --- Punto de integración con LangChain Orchestrator ---
        # Aquí es donde llamaremos a nuestro orquestador principal de LangChain
        # Le pasamos la lista de rutas a los documentos guardados.
        validation_results = await main_validation_chain_processor(document_paths)
        # --- Fin de la integración ---

        return {
            "status": "success",
            "message": "Documentos recibidos y en proceso de validación.",
            "results": validation_results # Esto contendrá el resultado de LangChain
        }
    except Exception as e:
        print(f"Error procesando documentos: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
    finally:
        # Opcional: limpiar los archivos temporales después de procesarlos
        # Para el MVP podemos dejarlos para depuración, luego implementar borrado seguro
        for path in document_paths:
             if os.path.exists(path):
                 os.remove(path)
                 print(f"Archivo temporal '{path}' eliminado.")