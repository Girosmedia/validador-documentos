# agents/validation.py
from typing import Dict, Any, List, Optional
import re
from datetime import datetime, date

async def validate_document_data_chain(doc_id: str, doc_type: str, extracted_data: Dict[str, Any], client_data: Dict[str, Any]) -> Dict[str, Any]:
    
    validation_status = "OK"  # Estado inicial optimista
    validation_errors = []
    
    print(f"  Validando datos para {doc_id} de tipo {doc_type}...")

    # Función auxiliar para agregar errores críticos
    def add_critical_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field,
            "message": message,
            "severity": "CRITICAL"
        })
        validation_status = "ERROR"

    # Función auxiliar para agregar errores que requieren revisión manual
    def add_manual_review_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field,
            "message": message,
            "severity": "MANUAL_REVIEW"
        })
        if validation_status == "OK":  # Solo cambiar si no existen errores críticos
            validation_status = "PENDIENTE_MANUAL"

    # --- Pre-procesar la fecha de curse del crédito ---
    solicitud_fecha_curse_obj: Optional[date] = None
    if client_data.get("solicitud_fecha_curse"):
        raw_date_str = client_data["solicitud_fecha_curse"]
        try:
            # Manejar formato ISO 8601 como "2025-05-30T00:00:00.000Z"
            if raw_date_str.endswith('Z'):
                solicitud_fecha_curse_obj = datetime.fromisoformat(raw_date_str.replace('Z', '')).date()
            else:
                solicitud_fecha_curse_obj = datetime.fromisoformat(raw_date_str).date()
        except ValueError:
            # Fallback para formato más simple YYYY-MM-DD si fromisoformat falla
            try:
                solicitud_fecha_curse_obj = datetime.strptime(raw_date_str, "%Y-%m-%d").date()
            except ValueError:
                add_critical_error("solicitud_fecha_curse", f"Formato inválido para la fecha de curse del crédito '{raw_date_str}'. Se esperaba ISO 8601 (ej: 2025-05-30T00:00:00.000Z) o YYYY-MM-DD.")
                solicitud_fecha_curse_obj = None # Asegurar que sea None si hay error de formato

    if solicitud_fecha_curse_obj is None and client_data.get("solicitud_fecha_curse") is not None:
        pass # El error crítico ya fue agregado por add_critical_error

    # --- Validaciones Específicas por Tipo de Documento ---

    if doc_type == "CEDULA_IDENTIDAD":
        # Validar campos críticos obligatorios
        critical_fields = ["nombre_completo", "run", "fecha_nacimiento", "fecha_vencimiento"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        # Comparación de datos del cliente con datos extraídos
        cliente_nombres_req = client_data.get("cliente_nombres", "").strip().lower()
        cliente_apellido_paterno_req = client_data.get("cliente_apellido_paterno", "").strip().lower()
        cliente_apellido_materno_req = client_data.get("cliente_apellido_materno", "").strip().lower()
        cliente_rut_req = client_data.get("cliente_rut", "").strip().replace(".", "").replace("-", "").lower()

        extracted_nombres = extracted_data.get("nombres", "").strip().lower()
        extracted_apellido_paterno = extracted_data.get("apellido_paterno", "").strip().lower()
        extracted_apellido_materno = extracted_data.get("apellido_materno", "").strip().lower()
        extracted_run_clean = extracted_data.get("run", "").strip().replace(".", "").replace("-", "").lower()

        if extracted_nombres and cliente_nombres_req and extracted_nombres != cliente_nombres_req:
            add_critical_error("nombres", f"Nombres del cliente '{cliente_nombres_req.upper()}' no coinciden con los extraídos '{extracted_nombres.upper()}'.")
        if extracted_apellido_paterno and cliente_apellido_paterno_req and extracted_apellido_paterno != cliente_apellido_paterno_req:
            add_critical_error("apellido_paterno", f"Apellido paterno del cliente '{cliente_apellido_paterno_req.upper()}' no coincide con el extraído '{extracted_apellido_paterno.upper()}'.")
        if extracted_apellido_materno and cliente_apellido_materno_req and extracted_apellido_materno != cliente_apellido_materno_req:
            add_critical_error("apellido_materno", f"Apellido materno del cliente '{cliente_apellido_materno_req.upper()}' no coincide con el extraído '{extracted_apellido_materno.upper()}'.")
        
        if extracted_run_clean and cliente_rut_req and extracted_run_clean != cliente_rut_req:
            add_critical_error("run", f"RUT del cliente '{cliente_rut_req.upper()}' no coincide con el extraído '{extracted_run_clean.upper()}'.")

        if extracted_data.get("run"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run"]):
                add_critical_error("run_format", f"Formato de RUN inválido '{extracted_data['run']}'.")

        if extracted_data.get("fecha_vencimiento"):
            try:
                doc_vencimiento_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d").date() 
                
                if solicitud_fecha_curse_obj:
                    if doc_vencimiento_obj < solicitud_fecha_curse_obj:
                        add_critical_error("fecha_vencimiento", f"Cédula de identidad vencida antes de la fecha de curse del crédito (vencimiento: {extracted_data['fecha_vencimiento']}, curse: {client_data.get('solicitud_fecha_curse', 'N/A')}).")
                else:
                    if doc_vencimiento_obj < datetime.now().date():
                        add_critical_error("fecha_vencimiento", f"Cédula de identidad vencida a la fecha de hoy (fecha de vencimiento: {extracted_data['fecha_vencimiento']}).")
            except ValueError:
                add_critical_error("fecha_vencimiento", f"Formato de fecha inválido para 'fecha_vencimiento': '{extracted_data['fecha_vencimiento']}'. Se esperaba YYYY-MM-DD.")
        else:
             add_critical_error("fecha_vencimiento", "Fecha de vencimiento no encontrada en la cédula de identidad.")

        for date_field in ["fecha_nacimiento", "fecha_emision"]:
            if extracted_data.get(date_field):
                try:
                    datetime.strptime(extracted_data[date_field], "%Y-%m-%d").date() 
                except ValueError:
                    add_critical_error(date_field, f"Formato de fecha inválido para '{date_field}': '{extracted_data[date_field]}'. Se esperaba YYYY-MM-DD.")

        if extracted_data.get("sexo") and extracted_data["sexo"].upper() not in ["M", "F"]:
            add_manual_review_error("sexo", f"Sexo '{extracted_data['sexo']}' no es 'M' o 'F'.")


    elif doc_type == "COMPROBANTE_DOMICILIO":
        critical_fields = ["nombre_titular", "direccion_completa", "empresa_emisora", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    days_diff_emission = (solicitud_fecha_curse_obj - emission_date_obj).days
                    if days_diff_emission < 0: 
                        add_critical_error("fecha_emision", f"Fecha de emisión del comprobante de domicilio ({extracted_data['fecha_emision']}) es futura respecto a la fecha de curse.")
                    elif days_diff_emission > 60:
                        add_critical_error("fecha_emision", f"Fecha de emisión del comprobante de domicilio es demasiado antigua ({days_diff_emission} días antes de la fecha de curse). Máximo permitido: 60 días.")
                else:
                    add_manual_review_error("fecha_emision", "No se puede validar la fecha de emisión contra la fecha de curse debido a que la fecha de curse es inválida o no existe.")
            except ValueError:
                add_critical_error("fecha_emision", f"Formato de fecha de emisión inválido '{extracted_data['fecha_emision']}'. Se esperaba YYYY-MM-DD.")
        else:
            add_critical_error("fecha_emision", "Fecha de emisión no encontrada en el Comprobante de Domicilio.")

        if extracted_data.get("fecha_vencimiento"):
            try:
                vencimiento_date_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    days_diff_vencimiento = (solicitud_fecha_curse_obj - vencimiento_date_obj).days
                    if days_diff_vencimiento > 10:
                        add_critical_error("fecha_vencimiento", f"Comprobante de domicilio vencido {days_diff_vencimiento} días antes de la fecha de curse. Máximo permitido: 10 días.")
                else:
                    add_manual_review_error("fecha_vencimiento", "No se puede validar la fecha de vencimiento contra la fecha de curse debido a que la fecha de curse es inválida o no existe.")
            except ValueError:
                add_critical_error("fecha_vencimiento", f"Formato de fecha de vencimiento inválido '{extracted_data['fecha_vencimiento']}'. Se esperaba YYYY-MM-DD.")
        
        cliente_nombres_req = client_data.get("cliente_nombres", "").strip().lower()
        cliente_apellido_paterno_req = client_data.get("cliente_apellido_paterno", "").strip().lower()
        cliente_apellido_materno_req = client_data.get("cliente_apellido_materno", "").strip().lower()
        
        extracted_nombres = extracted_data.get("nombres", "").strip().lower() # Asumiendo que el campo se llama 'nombres' en la extracción de comprobante de domicilio
        extracted_apellido_paterno = extracted_data.get("apellido_paterno", "").strip().lower()
        extracted_apellido_materno = extracted_data.get("apellido_materno", "").strip().lower()

        if extracted_nombres and cliente_nombres_req and extracted_nombres != cliente_nombres_req:
             add_critical_error("nombres", f"Nombres del titular en comprobante '{extracted_nombres.upper()}' no coinciden con los del cliente '{cliente_nombres_req.upper()}'.")
        if extracted_apellido_paterno and cliente_apellido_paterno_req and extracted_apellido_paterno != cliente_apellido_paterno_req:
             add_critical_error("apellido_paterno", f"Apellido paterno del titular en comprobante '{extracted_apellido_paterno.upper()}' no coincide con el del cliente '{cliente_apellido_paterno_req.upper()}'.")
        if extracted_apellido_materno and cliente_apellido_materno_req and extracted_apellido_materno != cliente_apellido_materno_req:
             add_critical_error("apellido_materno", f"Apellido materno del titular en comprobante '{extracted_apellido_materno.upper()}' no coincide con el del cliente '{cliente_apellido_materno_req.upper()}'.")


    elif doc_type == "CERTIFICADO_DEUDA":
        critical_fields = ["nombre_titular", "run_titular", "estado_deuda", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío.")
        
        extracted_run_titular_clean = extracted_data.get("run_titular", "").strip().replace(".", "").replace("-", "").lower()
        cliente_rut_req = client_data.get("cliente_rut", "").strip().replace(".", "").replace("-", "").lower()

        if extracted_run_titular_clean and cliente_rut_req and extracted_run_titular_clean != cliente_rut_req:
            add_critical_error("run_titular", f"RUT del titular del certificado '{extracted_run_titular_clean.upper()}' no coincide con el RUT del cliente '{cliente_rut_req.upper()}'.")
        elif not extracted_run_titular_clean:
            add_critical_error("run_titular", "RUT del titular del certificado no encontrado para validación.")

        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    if emission_date_obj != solicitud_fecha_curse_obj:
                        add_critical_error("fecha_emision", f"Fecha de emisión del certificado de deuda ({extracted_data['fecha_emision']}) debe ser exactamente la fecha de curse del crédito ({client_data.get('solicitud_fecha_curse', 'N/A')}).")
                else:
                    add_manual_review_error("fecha_emision", "No se puede validar la fecha de emisión contra la fecha de curse debido a que la fecha de curse es inválida o no existe.")
            except ValueError:
                add_critical_error("fecha_emision", f"Formato de fecha de emisión inválido '{extracted_data['fecha_emision']}'. Se esperaba YYYY-MM-DD.")
        else:
            add_critical_error("fecha_emision", "Fecha de emisión no encontrada en el Certificado de Deuda.")
        
        if extracted_data.get("estado_deuda"):
            estado_lower = extracted_data["estado_deuda"].lower()
            
            if "sin anotaciones" in estado_lower:
                pass 
            elif "con anotaciones" in estado_lower:
                add_critical_error("estado_deuda", "El certificado de deuda indica 'CON ANOTACIONES', lo cual es un error crítico.")
            else:
                add_manual_review_error("estado_deuda", f"Estado de deuda '{extracted_data['estado_deuda']}' es ambiguo. Se requiere revisión manual (se esperaba 'SIN ANOTACIONES' o 'CON ANOTACIONES').")
        else:
            add_critical_error("estado_deuda", "Estado de deuda no encontrado en el Certificado de Deuda.")


    elif doc_type == "REFERENCIAS_PERSONALES":
        if not isinstance(extracted_data, list):
            add_critical_error("extracted_data", "Las referencias no fueron extraídas como una lista.")
        else:
            min_references = 2
            if len(extracted_data) < min_references:
                add_critical_error("count", f"Se requieren al menos {min_references} referencias, pero se encontraron {len(extracted_data)}.")
            
            for i, ref in enumerate(extracted_data):
                if not ref.get("nombre_referencia"):
                    add_critical_error(f"reference_{i+1}.nombre_referencia", "Nombre de referencia obligatorio no encontrado.")
                
                telefono = ref.get("numero_telefono", "")
                if not telefono:
                    add_critical_error(f"reference_{i+1}.numero_telefono", "Número de teléfono obligatorio no encontrado.")
                else:
                    telefono_clean = telefono.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
                    if not re.fullmatch(r"^(?:56)?(?:9\d{8}|[2-8]\d{7})$", telefono_clean):
                        add_critical_error(f"reference_{i+1}.numero_telefono", f"Formato de teléfono chileno inválido '{telefono}'.")

    elif doc_type == "LIQUIDACION_SUELDO":
        critical_fields = ["nombre_empleado", "run_empleado", "rut_empresa", "nombre_empresa", "cargo", "periodo", "fecha_emision", "sueldo_bruto", "sueldo_liquido"]
        for field in critical_fields:
            if not extracted_data.get(field): # Check for None or empty string
                # Specific check for amount fields that could be 0 but valid.
                # For now, if any critical field is missing (None or empty string), it's an error.
                add_critical_error(field, f"Campo crítico '{field}' no encontrado o vacío en Liquidación de Sueldo.")

        if extracted_data.get("run_empleado"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run_empleado"]):
                add_critical_error("run_empleado", f"Formato de RUN de empleado inválido '{extracted_data['run_empleado']}'.")

        if extracted_data.get("rut_empresa"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["rut_empresa"]):
                add_critical_error("rut_empresa", f"Formato de RUT de empresa inválido '{extracted_data['rut_empresa']}'.")

        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    months_diff = (solicitud_fecha_curse_obj.year - emission_date_obj.year) * 12 + \
                                  (solicitud_fecha_curse_obj.month - emission_date_obj.month)
                    if months_diff > 3: 
                        add_critical_error("fecha_emision", f"Liquidación de sueldo es demasiado antigua ({months_diff} meses respecto a la fecha de curse). Máximo permitido: 3 meses.")
                    elif months_diff < 0: 
                        add_critical_error("fecha_emision", f"Fecha de emisión de liquidación de sueldo ({extracted_data['fecha_emision']}) es futura respecto a la fecha de curse.")
                    elif months_diff > 2: 
                        add_manual_review_error("fecha_emision", f"Liquidación de sueldo tiene {months_diff} meses de antigüedad respecto a la fecha de curse. Se recomienda revisión.")
                else:
                    # Fallback a fecha actual si fecha_curse es inválida/no existe
                    days_old = (datetime.now().date() - emission_date_obj).days
                    if days_old > 90: # Aprox 3 meses
                        add_critical_error("fecha_emision", f"Liquidación de sueldo es demasiado antigua ({days_old} días). Máximo permitido: 90 días.")
            except ValueError:
                add_critical_error("fecha_emision", f"Formato de fecha de emisión inválido '{extracted_data['fecha_emision']}'.")
        # No se añade error crítico si fecha_emision no existe aquí, ya que está cubierto por la validación de campos críticos al inicio de esta sección.

        # Validar campos de montos (sueldo_bruto y sueldo_liquido son críticos y ya validados arriba si están vacíos)
        # Esta validación es para el formato numérico si los campos existen.
        amount_fields_to_check_format = ["sueldo_bruto", "sueldo_liquido", "total_descuentos", "total_imposiciones"]
        for monto_field in amount_fields_to_check_format:
            field_value = extracted_data.get(monto_field)
            if field_value is not None and str(field_value).strip() != "": # Procede solo si hay un valor no vacío
                try:
                    clean_monto = str(field_value).replace(".", "").replace(",", ".")
                    float(clean_monto)
                except ValueError:
                    add_manual_review_error(monto_field, f"Valor para '{monto_field}' ('{field_value}') no es un número válido y requiere revisión manual.")
            elif monto_field in ["sueldo_bruto", "sueldo_liquido"] and (field_value is None or str(field_value).strip() == ""):
                # Esto ya está cubierto por la validación de campos críticos inicial, pero se mantiene por si acaso.
                 add_critical_error(monto_field, f"Campo crítico '{monto_field}' no encontrado o vacío en Liquidación de Sueldo.")


    elif doc_type == "OTRO" or doc_type == "unknown":
        add_manual_review_error("document_type", "Tipo de documento desconocido o no clasificado. Requiere revisión manual.")
    
    else:
        add_manual_review_error("document_type", f"Tipo de documento '{doc_type}' reconocido pero requiere validación manual.")

    # Registrar el resultado
    if validation_status == "OK":
        print(f"  {doc_id} validado exitosamente")
    elif validation_status == "ERROR":
        error_count = len([e for e in validation_errors if e.get("severity") == "CRITICAL"])
        print(f"  {doc_id} tiene {error_count} error(es) crítico(s)")
    else:  # PENDIENTE_MANUAL
        manual_count = len([e for e in validation_errors if e.get("severity") == "MANUAL_REVIEW"])
        print(f"  {doc_id} requiere revisión manual ({manual_count} ítem(s))")

    return {
        "validation_status": validation_status,
        "validation_errors": validation_errors
    }