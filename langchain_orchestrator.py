from typing import List, Dict, Any, Optional
import os
import json 
from datetime import datetime
from agents.preprocessing import preprocess_documents_chain
from agents.classification import classify_document_chain
from agents.extraction import extract_credit_data_chain
from agents.validation import validate_document_data_chain
from pydantic import BaseModel, Field # Asegúrate de que pydantic esté instalado

print("EN EL ORQUESTRADOR LANGCHAIN")

class DocumentBase64(BaseModel):
    filename: str
    base64_content: str
    content_type: str

def determine_global_status(document_results: Dict[str, Any]) -> str:

    if not document_results:
        return "RECHAZADA_REVISION_AUTOMATICA"
    
    # Contadores de estados
    ok_count = 0
    error_count = 0
    pending_manual_count = 0
    other_count = 0
    
    # Contar estados de validación
    for doc_id, doc_info in document_results.items():
        validation_status = doc_info.get('validation_status', 'ERROR')
        
        if validation_status in ['OK', 'APROBADO']:
            ok_count += 1
        elif validation_status in ['ERROR', 'FAILED_CRITICAL_ERROR']:
            error_count += 1
        elif validation_status in ['PENDIENTE_MANUAL', 'PENDIENTE_REVISION_MANUAL']:
            pending_manual_count += 1
        else:
            other_count += 1
    
    total_docs = len(document_results)
    
    # Aplicar lógica de decisión
    if pending_manual_count > 0 or other_count > 0:
        # Si hay al menos un documento pendiente de revisión manual
        return "PENDIENTE_REVISION_MANUAL"
    elif ok_count == total_docs:
        # Si todos los documentos están OK
        return "CURSADO"
    elif error_count == total_docs:
        # Si todos los documentos tienen errores
        return "RECHAZADA_REVISION_AUTOMATICA"
    else:
        # Mezcla de OK y ERROR -> requiere revisión manual
        return "PENDIENTE_REVISION_MANUAL"

def generate_global_summary(document_results: Dict[str, Any], global_status: str) -> Dict[str, Any]:

    status_counts = {}
    total_errors = 0
    error_summary = []
    
    for doc_id, doc_info in document_results.items():
        validation_status = doc_info.get('validation_status', 'ERROR')
        doc_type = doc_info.get('doc_type', 'UNKNOWN')
        
        # Contar estados
        if validation_status not in status_counts:
            status_counts[validation_status] = 0
        status_counts[validation_status] += 1
        
        # Recopilar errores
        validation_errors = doc_info.get('validation_errors', [])
        if validation_errors:
            total_errors += len(validation_errors)
            error_summary.append({
                "document_id": doc_id,
                "document_type": doc_type,
                "error_count": len(validation_errors),
                "errors": validation_errors
            })
    
    # Generar mensaje descriptivo según el estado
    if global_status == "CURSADO":
        status_message = "Todos los documentos han sido validados correctamente. La solicitud puede ser cursada."
    elif global_status == "PENDIENTE_REVISION_MANUAL":
        pending_count = status_counts.get('PENDIENTE_MANUAL', 0) + status_counts.get('PENDIENTE_REVISION_MANUAL', 0)
        if pending_count > 0:
            status_message = f"La solicitud requiere revisión manual debido a {pending_count} documento(s) con validaciones pendientes."
        else:
            status_message = "La solicitud requiere revisión manual debido a una mezcla de documentos válidos y con errores."
    else:  # RECHAZADA_REVISION_AUTOMATICA
        status_message = f"La solicitud ha sido rechazada automáticamente. Se encontraron errores en todos los documentos ({total_errors} errores en total)."
    
    return {
        "overall_status": global_status,
        "status_message": status_message,
        "document_status_summary": status_counts,
        "total_documents": len(document_results),
        "total_errors": total_errors,
        "documents_with_errors": len(error_summary),
        "error_details": error_summary if error_summary else None
    }


async def main_validation_chain_processor(
    documents_base64_payload: List[DocumentBase64], # ¡Ahora recibe el payload Base64!
    client_data: Dict[str, Any] 
) -> Dict[str, Any]:

    print(f"Orquestador LangChain iniciado para {len(documents_base64_payload)} documentos Base64.")
    print(f"Datos del cliente para validación: {json.dumps(client_data, indent=2)}")
    
    all_processed_docs_data = {}
    final_document_results = {}
    
    try:
        # --- Paso 1: Preprocesamiento de Documentos ---
        print("\n--- Ejecutando Paso 1: Preprocesamiento de Documentos (Base64 a texto/imágenes) ---")
        # ¡Pasamos el payload completo al preprocesamiento!
        processed_data_by_doc = await preprocess_documents_chain(documents_base64_payload)
        all_processed_docs_data.update(processed_data_by_doc)

        # --- Procesamiento de cada documento ---
        for doc_id, doc_info in all_processed_docs_data.items():
            print(f"\n--- Procesando documento: {doc_id} ---")
            
            if doc_info["status"] not in ["processed_llm_ocr", "processed_digital_pdf"]:
                doc_info['validation_status'] = "ERROR"
                doc_info['validation_errors'] = [{
                    "field": "preprocessing", 
                    "message": f"Error en preprocesamiento: {doc_info.get('error_message', 'Error desconocido')}"
                }]
                final_document_results[doc_id] = doc_info
                print(f"    ❌ Error en preprocesamiento de {doc_id}")
                continue

            # --- Paso 2: Clasificación ---
            print(f"    📋 Clasificando {doc_id}...")
            classification_result = await classify_document_chain(raw_text=doc_info["raw_text"])
            doc_info.update(classification_result)

            if doc_info["classification_status"] != "classified":
                doc_info['validation_status'] = "ERROR"
                doc_info['validation_errors'] = [{
                    "field": "classification", 
                    "message": f"Error en clasificación: {doc_info.get('classification_error', 'Error desconocido')}"
                }]
                final_document_results[doc_id] = doc_info
                print(f"    ❌ Error en clasificación de {doc_id}")
                continue

            print(f"    ✅ {doc_id} clasificado como: {doc_info['doc_type']}")

            # --- Paso 3: Extracción ---
            print(f"    🔍 Extrayendo datos de {doc_id}...")

            original_doc_b64 = next((d for d in documents_base64_payload if d.filename == doc_id), None)
            
            if original_doc_b64:
                extraction_result = await extract_credit_data_chain(
                    raw_text=doc_info["raw_text"], # Se sigue pasando el texto preprocesado
                    doc_type=doc_info["doc_type"],
                    base64_content=original_doc_b64.base64_content, # Pasamos el Base64 original
                    content_type=original_doc_b64.content_type # Pasamos el content_type original
                )
                doc_info.update(extraction_result)
            else:
                # Esto no debería pasar si el flujo es correcto
                doc_info['extraction_status'] = "failed"
                doc_info['extraction_error'] = "Documento Base64 original no encontrado en el payload."
                print(f"    ❌ ERROR: Documento Base64 original para {doc_id} no encontrado.")


            if doc_info["extraction_status"] != "extracted" and doc_info["extraction_status"] != "extracted_raw_text":
                doc_info['validation_status'] = "ERROR"
                doc_info['validation_errors'] = [{
                    "field": "extraction", 
                    "message": f"Error en extracción: {doc_info.get('extraction_error', 'Error desconocido')}"
                }]
                final_document_results[doc_id] = doc_info
                print(f"    ❌ Error en extracción de {doc_id}")
                continue

            print(f"    ✅ Datos extraídos de {doc_id}")

            # --- Paso 4: Validación ---
            print(f"    ✔️ Validando {doc_id}...")
            validation_result = await validate_document_data_chain(
                doc_id=doc_id, 
                doc_type=doc_info["doc_type"],
                extracted_data=doc_info["extracted_data"],
                client_data=client_data 
            )
            doc_info.update(validation_result)

            final_document_results[doc_id] = doc_info
            print(f"    📊 Estado de validación para {doc_id}: {doc_info['validation_status']}")

        # --- Paso 5: Determinación del Estado Global ---
        print("\n--- Determinando Estado Global de la Solicitud ---")
        global_status = determine_global_status(final_document_results)
        global_summary = generate_global_summary(final_document_results, global_status)
        
        print(f"--- Estado Global Final: {global_status} ---")
        print(f"--- Resumen: {global_summary['status_message']} ---")

        return {
            "validation_status": global_status,
            "document_results": final_document_results,
            "global_summary": global_summary
        }

    except Exception as e:
        print(f"Error crítico en el orquestador: {e}")
        return {
            "validation_status": "FAILED_CRITICAL_ERROR",
            "error_message": str(e),
            "document_results": final_document_results, # Incluir resultados parciales para depuración
            "global_summary": {
                "overall_status": "FAILED_CRITICAL_ERROR",
                "status_message": f"Error crítico en el procesamiento: {str(e)}",
                "document_status_summary": {},
                "total_documents": len(final_document_results),
                "total_errors": 1,
                "documents_with_errors": 0,
                "error_details": None
            }
        }