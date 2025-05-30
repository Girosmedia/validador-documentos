# # agents/validation.py
# from typing import Dict, Any, List
# import re
# from datetime import datetime

# async def validate_document_data_chain(doc_id: str, doc_type: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Agente/Cadena de validación de reglas de negocio para los datos extraídos de un solo documento.

#     Args:
#         doc_id (str): ID del documento.
#         doc_type (str): Tipo de documento clasificado.
#         extracted_data (Dict[str, Any]): Datos extraídos del documento en formato JSON.

#     Returns:
#         Dict[str, Any]: Diccionario con el estado de validación y la lista de errores/hallazgos.
#     """
#     validation_status = "PENDIENTE_VALIDACION"  # Estado inicial
#     validation_errors = []
    
#     print(f"    📝 Validando datos para {doc_id} de tipo {doc_type}...")

#     # Función auxiliar para añadir errores
#     def add_error(field: str, message: str):
#         nonlocal validation_status
#         validation_errors.append({"field": field, "message": message})
#         validation_status = "ERROR"

#     # --- Validaciones Específicas por Tipo de Documento ---

#     if doc_type == "CEDULA_IDENTIDAD":
#         # Validar campos obligatorios
#         required_fields = ["nombre_completo", "run", "fecha_nacimiento", "fecha_vencimiento", "sexo"]
#         for field in required_fields:
#             if not extracted_data.get(field):
#                 add_error(field, f"Campo obligatorio '{field}' no encontrado o vacío.")
        
#         # Validar formato RUN (simplificado)
#         if extracted_data.get("run"):
#             # Expresión regular para RUN chileno (ej. 12.345.678-9 o 12345678-9)
#             if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run"]):
#                 add_error("run", f"Formato de RUN '{extracted_data['run']}' inválido.")
#             # Se podría añadir una validación de dígito verificador real aquí si es necesario

#         # Validar fechas
#         for date_field in ["fecha_nacimiento", "fecha_emision", "fecha_vencimiento"]:
#             if extracted_data.get(date_field):
#                 try:
#                     # Intentar parsear la fecha en formato YYYY-MM-DD
#                     date_obj = datetime.strptime(extracted_data[date_field], "%Y-%m-%d")
                    
#                     if date_field == "fecha_vencimiento":
#                         # Validar que la cédula no esté vencida
#                         if date_obj < datetime.now():
#                             add_error(date_field, f"La cédula está vencida (fecha de vencimiento: {extracted_data[date_field]}).")
#                 except ValueError:
#                     add_error(date_field, f"Formato de fecha '{extracted_data[date_field]}' inválido. Se espera YYYY-MM-DD.")
#             elif date_field in ["fecha_nacimiento", "fecha_vencimiento"]:
#                  add_error(date_field, f"Campo obligatorio de fecha '{date_field}' no encontrado o inválido.")

#         # Validar sexo
#         if extracted_data.get("sexo") and extracted_data["sexo"].upper() not in ["M", "F"]:
#             add_error("sexo", f"El sexo '{extracted_data['sexo']}' no es 'M' o 'F'.")

#     elif doc_type == "COMPROBANTE_DOMICILIO":
#         # Validar campos obligatorios
#         required_fields = ["nombre_titular", "direccion_completa", "empresa_emisora", "fecha_emision", "monto_total_pagar"]
#         for field in required_fields:
#             if not extracted_data.get(field):
#                 add_error(field, f"Campo obligatorio '{field}' no encontrado o vacío.")
        
#         # Validar fecha de emisión no sea demasiado antigua (ej. últimos 90 días)
#         if extracted_data.get("fecha_emision"):
#             try:
#                 emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d")
#                 if (datetime.now() - emission_date_obj).days > 60:
#                     add_error("fecha_emision", f"Comprobante de domicilio demasiado antiguo (emitido hace más de 90 días).")
#             except ValueError:
#                 add_error("fecha_emision", f"Formato de fecha de emisión '{extracted_data['fecha_emision']}' inválido.")

#         # Validar fecha de vencimiento no sea demasiado antigua (ej. últimos 10 días)
#         if extracted_data.get("fecha_vencimiento"):
#             try:
#                 vencimiento_date_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d")
#                 if (datetime.now() - vencimiento_date_obj).days > 10:
#                     add_error("fecha_vencimiento", f"Comprobante de domicilio demasiado antiguo (emitido hace más de 10 días).")
#             except ValueError:
#                 add_error("fecha_vencimiento", f"Formato de fecha de vencimiento '{extracted_data['fecha_vencimiento']}' inválido.")

    
#     elif doc_type == "CERTIFICADO_DEUDA":
#         required_fields = ["nombre_titular", "run_titular", "estado_deuda", "fecha_emision"]
#         for field in required_fields:
#             if not extracted_data.get(field):
#                 add_error(field, f"Campo obligatorio '{field}' no encontrado o vacío.")
        
#         # Validar estado de deuda
#         if extracted_data.get("estado_deuda"):
#             if "vigente" in extracted_data["estado_deuda"].lower() and "sin" not in extracted_data["estado_deuda"].lower():
#                 add_error("estado_deuda", "El certificado indica deuda vigente.")

#     elif doc_type == "REFERENCIAS_PERSONALES":
#         # Validar que sea una lista y que tenga al menos N referencias
#         if not isinstance(extracted_data, list):
#             add_error("extracted_data", "Las referencias no se extrajeron como una lista.")
#         else:
#             min_references = 2 # Ejemplo: requerir al menos 2 referencias
#             if len(extracted_data) < min_references:
#                 add_error("count", f"Se requieren al menos {min_references} referencias, pero se encontraron {len(extracted_data)}.")
            
#             for i, ref in enumerate(extracted_data):
#                 if not ref.get("nombre_referencia"):
#                     add_error(f"referencia_{i+1}.nombre_referencia", "Nombre de referencia obligatorio no encontrado.")
#                 if not ref.get("numero_telefono") or not re.fullmatch(r"^\+?56\d{1}\s?\d{4}\s?\d{4}$", ref["numero_telefono"].replace(" ", "")): # Simple validación de formato chileno
#                     add_error(f"referencia_{i+1}.numero_telefono", f"Número de teléfono '{ref.get('numero_telefono')}' inválido o formato incorrecto.")
#                 # Aquí se podría añadir validación para la relación si se considera obligatoria

#     elif doc_type == "OTRO" or doc_type == "unknown":
#         validation_status = "PENDIENTE_MANUAL"
#         add_error("document_type", "Tipo de documento desconocido o no clasificado. Requiere revisión manual.")
    
#     else: # Si el doc_type no está en la lista de tipos específicos
#         validation_status = "PENDIENTE_MANUAL"
#         add_error("document_type", f"Tipo de documento '{doc_type}' reconocido pero no tiene reglas de validación específicas. Requiere revisión manual.")

#     if not validation_errors:
#         validation_status = "APROBADO"
#     elif any(err["message"] == "Campo obligatorio" for err in validation_errors): # Si falta un campo obligatorio
#         validation_status = "ERROR" # El status ya se setea a ERROR si se añade un error.
#     else:
#         validation_status = "PENDIENTE_REVISION_MANUAL" # Si hay errores, pero no críticos para el crédito (se podría definir mejor esto)


#     return {
#         "validation_status": validation_status,
#         "validation_errors": validation_errors
#     }


# agents/validation.py
from typing import Dict, Any, List
import re
from datetime import datetime

async def validate_document_data_chain(doc_id: str, doc_type: str, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agente/Cadena de validación de reglas de negocio para los datos extraídos de un solo documento.

    Args:
        doc_id (str): ID del documento.
        doc_type (str): Tipo de documento clasificado.
        extracted_data (Dict[str, Any]): Datos extraídos del documento en formato JSON.

    Returns:
        Dict[str, Any]: Diccionario con el estado de validación y la lista de errores/hallazgos.
        
    Estados posibles:
    - OK: Documento válido sin errores
    - ERROR: Documento con errores críticos que impiden su aceptación
    - PENDIENTE_MANUAL: Documento requiere revisión manual (errores no críticos o casos especiales)
    """
    validation_status = "OK"  # Estado inicial optimista
    validation_errors = []
    
    print(f"    📝 Validando datos para {doc_id} de tipo {doc_type}...")

    # Función auxiliar para añadir errores críticos
    def add_critical_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field, 
            "message": message, 
            "severity": "CRITICAL"
        })
        validation_status = "ERROR"

    # Función auxiliar para añadir errores que requieren revisión manual
    def add_manual_review_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field, 
            "message": message, 
            "severity": "MANUAL_REVIEW"
        })
        if validation_status == "OK":  # Solo cambiar si no hay errores críticos
            validation_status = "PENDIENTE_MANUAL"

    # --- Validaciones Específicas por Tipo de Documento ---

    if doc_type == "CEDULA_IDENTIDAD":
        # Validar campos obligatorios críticos
        critical_fields = ["nombre_completo", "run", "fecha_nacimiento", "fecha_vencimiento"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        # Validar formato RUN (crítico)
        if extracted_data.get("run"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run"]):
                add_critical_error("run", f"Formato de RUN '{extracted_data['run']}' inválido.")

        # Validar fechas
        for date_field in ["fecha_nacimiento", "fecha_emision", "fecha_vencimiento"]:
            if extracted_data.get(date_field):
                try:
                    date_obj = datetime.strptime(extracted_data[date_field], "%Y-%m-%d")
                    
                    if date_field == "fecha_vencimiento":
                        # Cédula vencida es error crítico
                        if date_obj < datetime.now():
                            add_critical_error(date_field, f"La cédula está vencida (fecha de vencimiento: {extracted_data[date_field]}).")
                except ValueError:
                    add_critical_error(date_field, f"Formato de fecha '{extracted_data[date_field]}' inválido.")

        # Validar sexo (no crítico, pero puede requerir revisión)
        if extracted_data.get("sexo") and extracted_data["sexo"].upper() not in ["M", "F"]:
            add_manual_review_error("sexo", f"El sexo '{extracted_data['sexo']}' no es 'M' o 'F'.")

    elif doc_type == "COMPROBANTE_DOMICILIO":
        # Campos críticos
        critical_fields = ["nombre_titular", "direccion_completa", "empresa_emisora", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        # Validar antiguedad del comprobante
        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d")
                days_old = (datetime.now() - emission_date_obj).days
                
                if days_old > 90:
                    # Muy antiguo = error crítico
                    add_critical_error("fecha_emision", f"Comprobante demasiado antiguo ({days_old} días). Máximo permitido: 90 días.")
                elif days_old > 60:
                    # Antiguo pero no crítico = revisión manual
                    add_manual_review_error("fecha_emision", f"Comprobante tiene {days_old} días de antigüedad. Recomendado menos de 60 días.")
            except ValueError:
                add_critical_error("fecha_emision", f"Formato de fecha de emisión '{extracted_data['fecha_emision']}' inválido.")

        # Validar fecha de vencimiento
        if extracted_data.get("fecha_vencimiento"):
            try:
                vencimiento_date_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d")
                days_overdue = (datetime.now() - vencimiento_date_obj).days
                
                if days_overdue > 30:
                    # Muy vencido = error crítico
                    add_critical_error("fecha_vencimiento", f"Comprobante vencido hace {days_overdue} días. Máximo permitido: 30 días.")
                elif days_overdue > 10:
                    # Vencido pero no crítico = revisión manual
                    add_manual_review_error("fecha_vencimiento", f"Comprobante vencido hace {days_overdue} días. Recomendado menos de 10 días.")
            except ValueError:
                add_critical_error("fecha_vencimiento", f"Formato de fecha de vencimiento '{extracted_data['fecha_vencimiento']}' inválido.")

    elif doc_type == "CERTIFICADO_DEUDA":
        # Campos críticos
        critical_fields = ["nombre_titular", "run_titular", "estado_deuda", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        # Validar estado de deuda (crítico si tiene deudas vigentes)
        if extracted_data.get("estado_deuda"):
            estado_lower = extracted_data["estado_deuda"].lower()
            if "vigente" in estado_lower and "sin" not in estado_lower and "no" not in estado_lower:
                add_critical_error("estado_deuda", "El certificado indica deuda vigente.")

        # Validar antigüedad del certificado
        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d")
                days_old = (datetime.now() - emission_date_obj).days
                
                if days_old > 30:
                    add_manual_review_error("fecha_emision", f"Certificado de deuda tiene {days_old} días de antigüedad.")
            except ValueError:
                add_critical_error("fecha_emision", f"Formato de fecha de emisión inválido.")

    elif doc_type == "REFERENCIAS_PERSONALES":
        # Validar estructura
        if not isinstance(extracted_data, list):
            add_critical_error("extracted_data", "Las referencias no se extrajeron como una lista.")
        else:
            min_references = 2
            if len(extracted_data) < min_references:
                add_critical_error("count", f"Se requieren al menos {min_references} referencias, se encontraron {len(extracted_data)}.")
            
            for i, ref in enumerate(extracted_data):
                # Nombre es crítico
                if not ref.get("nombre_referencia"):
                    add_critical_error(f"referencia_{i+1}.nombre_referencia", "Nombre de referencia obligatorio no encontrado.")
                
                # Teléfono es crítico
                telefono = ref.get("numero_telefono", "")
                if not telefono:
                    add_critical_error(f"referencia_{i+1}.numero_telefono", "Número de teléfono obligatorio no encontrado.")
                else:
                    # Validación de formato chileno simplificada
                    telefono_clean = telefono.replace(" ", "").replace("-", "")
                    if not re.fullmatch(r"^\+?56[2-9]\d{8}$", telefono_clean):
                        add_manual_review_error(f"referencia_{i+1}.numero_telefono", f"Formato de teléfono '{telefono}' requiere verificación.")

    elif doc_type == "OTRO" or doc_type == "unknown":
        add_manual_review_error("document_type", "Tipo de documento desconocido o no clasificado. Requiere revisión manual.")
    
    else:
        # Tipo reconocido pero sin validaciones específicas
        add_manual_review_error("document_type", f"Tipo de documento '{doc_type}' reconocido pero requiere validación manual.")

    # Log del resultado
    if validation_status == "OK":
        print(f"    ✅ {doc_id} validado correctamente")
    elif validation_status == "ERROR":
        error_count = len([e for e in validation_errors if e.get("severity") == "CRITICAL"])
        print(f"    ❌ {doc_id} tiene {error_count} error(es) crítico(s)")
    else:  # PENDIENTE_MANUAL
        manual_count = len([e for e in validation_errors if e.get("severity") == "MANUAL_REVIEW"])
        print(f"    ⚠️ {doc_id} requiere revisión manual ({manual_count} item(s))")

    return {
        "validation_status": validation_status,
        "validation_errors": validation_errors
    }