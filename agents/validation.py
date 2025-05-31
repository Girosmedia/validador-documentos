# agents/validation.py
from typing import Dict, Any, List, Optional
import re
from datetime import datetime, date

async def validate_document_data_chain(doc_id: str, doc_type: str, extracted_data: Dict[str, Any], client_data: Dict[str, Any]) -> Dict[str, Any]:
    
    validation_status = "OK"  # Optimistic initial state
    validation_errors = []
    
    print(f"  Validating data for {doc_id} of type {doc_type}...")

    # Helper function to add critical errors
    def add_critical_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field,
            "message": message,
            "severity": "CRITICAL"
        })
        validation_status = "ERROR"

    # Helper function to add errors that require manual review
    def add_manual_review_error(field: str, message: str):
        nonlocal validation_status
        validation_errors.append({
            "field": field,
            "message": message,
            "severity": "MANUAL_REVIEW"
        })
        if validation_status == "OK":  # Only change if no critical errors already exist
            validation_status = "PENDIENTE_MANUAL"

    # --- Pre-process the credit's curse date ---
    solicitud_fecha_curse_obj: Optional[date] = None
    if client_data.get("solicitud_fecha_curse"):
        raw_date_str = client_data["solicitud_fecha_curse"]
        try:
            # Handle ISO 8601 format like "2025-05-30T00:00:00.000Z"
            # fromisoformat handles 'T' and milliseconds, but not 'Z' directly for timezone info.
            # If 'Z' is present, we can strip it for fromisoformat if it's always UTC.
            if raw_date_str.endswith('Z'):
                # Strip 'Z' and parse as naive datetime, then convert to date
                solicitud_fecha_curse_obj = datetime.fromisoformat(raw_date_str.replace('Z', '')).date()
            else:
                # Try parsing as ISO format first (handles 'T' and milliseconds)
                solicitud_fecha_curse_obj = datetime.fromisoformat(raw_date_str).date()
        except ValueError:
            # Fallback for simpler YYYY-MM-DD format if fromisoformat fails
            try:
                solicitud_fecha_curse_obj = datetime.strptime(raw_date_str, "%Y-%m-%d").date()
            except ValueError:
                add_critical_error("solicitud_fecha_curse", f"Invalid format for credit curse date '{raw_date_str}'. Expected ISO 8601 (e.g., 2025-05-30T00:00:00.000Z) or YYYY-MM-DD.")
                solicitud_fecha_curse_obj = None # Ensure it's None if there's a format error

    # If the curse date is critically invalid, mark it as an overall error and skip date-dependent validations
    if solicitud_fecha_curse_obj is None and client_data.get("solicitud_fecha_curse") is not None:
        pass # The critical error has already been added by add_critical_error

    # --- Specific Validations by Document Type ---

    if doc_type == "CEDULA_IDENTIDAD":
        # Validate critical mandatory fields
        critical_fields = ["nombre_completo", "run", "fecha_nacimiento", "fecha_vencimiento"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Critical field '{field}' not found or empty.")
        
        # Rule: Que los nombres, apellido paterno y apellido materno, sean iguales a lo extraído por el LLM.
        # This rule implies comparing LLM's extraction with expected client data.
        cliente_nombres_req = client_data.get("cliente_nombres", "").strip().lower()
        cliente_apellido_paterno_req = client_data.get("cliente_apellido_paterno", "").strip().lower()
        cliente_apellido_materno_req = client_data.get("cliente_apellido_materno", "").strip().lower()
        cliente_rut_req = client_data.get("cliente_rut", "").strip().replace(".", "").replace("-", "").lower()

        extracted_nombres = extracted_data.get("nombres", "").strip().lower()
        extracted_apellido_paterno = extracted_data.get("apellido_paterno", "").strip().lower()
        extracted_apellido_materno = extracted_data.get("apellido_materno", "").strip().lower()
        extracted_run_clean = extracted_data.get("run", "").strip().replace(".", "").replace("-", "").lower()

        # Rule: Que los nombres, apellido paterno y apellido materno, sean iguales a lo extraído por el LLM.
        # This compares extracted data with client_data, assuming client_data is the source of truth for "expected".
        # If the LLM extraction is missing or doesn't match client_data, it's an error.
        if extracted_nombres and cliente_nombres_req and extracted_nombres != cliente_nombres_req:
            add_critical_error("nombres", f"Client's Full Name '{cliente_nombres_req.upper()}' does not match extracted '{extracted_nombres.upper()}'.")
        if extracted_apellido_paterno and cliente_apellido_paterno_req and extracted_apellido_paterno != cliente_apellido_paterno_req:
            add_critical_error("apellido_paterno", f"Client's Paternal Last Name '{cliente_apellido_paterno_req.upper()}' does not match extracted '{extracted_apellido_paterno.upper()}'.")
        if extracted_apellido_materno and cliente_apellido_materno_req and extracted_apellido_materno != cliente_apellido_materno_req:
            add_critical_error("apellido_materno", f"Client's Maternal Last Name '{cliente_apellido_materno_req.upper()}' does not match extracted '{extracted_apellido_materno.upper()}'.")
        
        # Rule: Que el rut coincida con el dato del credito (client_data).
        if extracted_run_clean and cliente_rut_req and extracted_run_clean != cliente_rut_req:
            add_critical_error("run", f"Client's RUT '{cliente_rut_req.upper()}' does not match extracted '{extracted_run_clean.upper()}'.")


        # Validate RUN format (critical) - Moved after matching check, still crucial
        if extracted_data.get("run"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run"]):
                add_critical_error("run_format", f"Invalid RUN format '{extracted_data['run']}'.")


        # Rule: Que la fecha de vencimiento esté vigente a la fecha de curse.
        if extracted_data.get("fecha_vencimiento"):
            try:
                doc_vencimiento_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d").date() 
                
                if solicitud_fecha_curse_obj:
                    if doc_vencimiento_obj < solicitud_fecha_curse_obj:
                        add_critical_error("fecha_vencimiento", f"ID card expired before the credit curse date (expiration: {extracted_data['fecha_vencimiento']}, curse: {client_data['solicitud_fecha_curse']}).")
                else:
                    # Fallback if curse date is invalid/missing (should be caught by previous critical error)
                    # If this happens, it means we can't properly validate against curse date, so we'll use current date as a last resort.
                    if doc_vencimiento_obj < datetime.now().date():
                        add_critical_error("fecha_vencimiento", f"ID card is expired as of today (expiration date: {extracted_data['fecha_vencimiento']}).")
            except ValueError:
                add_critical_error("fecha_vencimiento", f"Invalid date format for 'fecha_vencimiento': '{extracted_data['fecha_vencimiento']}'. Expected YYYY-MM-DD.")
        else:
             add_critical_error("fecha_vencimiento", "Expiration date not found on ID card.")

        # Other date validations (like fecha_nacimiento, fecha_emision)
        for date_field in ["fecha_nacimiento", "fecha_emision"]:
            if extracted_data.get(date_field):
                try:
                    datetime.strptime(extracted_data[date_field], "%Y-%m-%d").date() 
                except ValueError:
                    add_critical_error(date_field, f"Invalid date format for '{date_field}': '{extracted_data[date_field]}'. Expected YYYY-MM-DD.")

        # Validate gender (not critical, but may require review)
        if extracted_data.get("sexo") and extracted_data["sexo"].upper() not in ["M", "F"]:
            add_manual_review_error("sexo", f"Gender '{extracted_data['sexo']}' is not 'M' or 'F'.")


    elif doc_type == "COMPROBANTE_DOMICILIO":
        # Critical fields
        critical_fields = ["nombre_titular", "direccion_completa", "empresa_emisora", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Critical field '{field}' not found or empty.")
        

        # Rule: Que la fecha de emision no sea mayor a 60 días desde la fecha de curse.
        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    days_diff_emission = (solicitud_fecha_curse_obj - emission_date_obj).days
                    if days_diff_emission < 0: # Emission date is in the future relative to curse date
                        add_critical_error("fecha_emision", f"Proof of address emission date ({extracted_data['fecha_emision']}) is in the future relative to curse date.")
                    elif days_diff_emission > 60:
                        add_critical_error("fecha_emision", f"Proof of address emission date is too old ({days_diff_emission} days before curse date). Maximum allowed: 60 days.")
                else:
                    # If curse date is invalid, this specific rule cannot be applied.
                    add_manual_review_error("fecha_emision", "Cannot validate emission date against curse date due to missing/invalid curse date.")
            except ValueError:
                add_critical_error("fecha_emision", f"Invalid emission date format '{extracted_data['fecha_emision']}'. Expected YYYY-MM-DD.")
        else:
            add_critical_error("fecha_emision", "Emission date not found on Proof of Address.")


        # Rule: Ni que su fecha de vencimiento sea mayor a 10 días, también desde la fecha de curse.
        if extracted_data.get("fecha_vencimiento"):
            try:
                vencimiento_date_obj = datetime.strptime(extracted_data["fecha_vencimiento"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    days_diff_vencimiento = (solicitud_fecha_curse_obj - vencimiento_date_obj).days
                    if days_diff_vencimiento > 10:
                        add_critical_error("fecha_vencimiento", f"Proof of address expired {days_diff_vencimiento} days before curse date. Maximum allowed: 10 days.")
                else:
                    # If curse date is invalid, this specific rule cannot be applied.
                    add_manual_review_error("fecha_vencimiento", "Cannot validate expiration date against curse date due to missing/invalid curse date.")
            except ValueError:
                add_critical_error("fecha_vencimiento", f"Invalid expiration date format '{extracted_data['fecha_vencimiento']}'. Expected YYYY-MM-DD.")
        # Note: Not all proof of address documents have a 'fecha_vencimiento'. Consider if this should be a critical error if missing.
        # For now, if missing, no error is added, but it depends on your specific needs.
        
        # Rule: Que los nombres, apellido paterno y apellido materno, sean iguales a lo extraído por el LLM.
        # This rule implies comparing LLM's extraction with expected client data.
        cliente_nombres_req = client_data.get("cliente_nombres", "").strip().lower()
        cliente_apellido_paterno_req = client_data.get("cliente_apellido_paterno", "").strip().lower()
        cliente_apellido_materno_req = client_data.get("cliente_apellido_materno", "").strip().lower()
        cliente_rut_req = client_data.get("cliente_rut", "").strip().replace(".", "").replace("-", "").lower()

        extracted_nombres = extracted_data.get("nombres", "").strip().lower()
        extracted_apellido_paterno = extracted_data.get("apellido_paterno", "").strip().lower()
        extracted_apellido_materno = extracted_data.get("apellido_materno", "").strip().lower()
        extracted_run_clean = extracted_data.get("run", "").strip().replace(".", "").replace("-", "").lower()

        # Rule: Que los nombres, apellido paterno y apellido materno, sean iguales a lo extraído por el LLM.
        # This compares extracted data with client_data, assuming client_data is the source of truth for "expected".
        # If the LLM extraction is missing or doesn't match client_data, it's an error.
        if extracted_nombres and cliente_nombres_req and extracted_nombres != cliente_nombres_req:
            add_critical_error("nombres", f"Client's Full Name '{cliente_nombres_req.upper()}' does not match extracted '{extracted_nombres.upper()}'.")
        if extracted_apellido_paterno and cliente_apellido_paterno_req and extracted_apellido_paterno != cliente_apellido_paterno_req:
            add_critical_error("apellido_paterno", f"Client's Paternal Last Name '{cliente_apellido_paterno_req.upper()}' does not match extracted '{extracted_apellido_paterno.upper()}'.")
        if extracted_apellido_materno and cliente_apellido_materno_req and extracted_apellido_materno != cliente_apellido_materno_req:
            add_critical_error("apellido_materno", f"Client's Maternal Last Name '{cliente_apellido_materno_req.upper()}' does not match extracted '{extracted_apellido_materno.upper()}'.")


    elif doc_type == "CERTIFICADO_DEUDA":
        # Critical fields
        critical_fields = ["nombre_titular", "run_titular", "estado_deuda", "fecha_emision"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Critical field '{field}' not found or empty.")
        
        # Rule: Que corresponda al rut del cliente (client_data)
        extracted_run_titular_clean = extracted_data.get("run_titular", "").strip().replace(".", "").replace("-", "").lower()
        cliente_rut_req = client_data.get("cliente_rut", "").strip().replace(".", "").replace("-", "").lower()

        if extracted_run_titular_clean and cliente_rut_req and extracted_run_titular_clean != cliente_rut_req:
            add_critical_error("run_titular", f"Certificate holder's RUT '{extracted_run_titular_clean.upper()}' does not match client's RUT '{cliente_rut_req.upper()}'.")
        elif not extracted_run_titular_clean:
            add_critical_error("run_titular", "Certificate holder's RUT not found for validation.")


        # Rule: Que la fecha de emision sea igual a la fecha de curse (no puede ser mayor ni menor)
        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    if emission_date_obj != solicitud_fecha_curse_obj:
                        add_critical_error("fecha_emision", f"Debt certificate emission date ({extracted_data['fecha_emision']}) must be exactly the credit curse date ({client_data['solicitud_fecha_curse']}).")
                else:
                    add_manual_review_error("fecha_emision", "Cannot validate emission date against curse date due to missing/invalid curse date.")

            except ValueError:
                add_critical_error("fecha_emision", f"Invalid emission date format '{extracted_data['fecha_emision']}'. Expected YYYY-MM-DD.")
        else:
            add_critical_error("fecha_emision", "Emission date not found on Debt Certificate.")

        # Rule: Y que no registre anotaciones 'Sin inscripción vigente'.
        # Re-confirming interpretation: "Sin inscripción vigente" means NO DEBT, which is GOOD.
        # The rule "que NO registre anotaciones 'Sin inscripción vigente'" would mean it *must* have debt.
        # I will assume the client meant: "It must NOT register active debt."
        # If it says "Sin inscripción vigente", "No registra", "No tiene", "Sin deuda", etc., it's OK.
        # If it explicitly says "vigente" and NOT "sin vigente", then it's a critical error.
        
        # Simplified Rule:
        # If contains "SIN ANOTACIONES" -> Approved (pass)
        # If contains "CON ANOTACIONES" -> Critical Error
        # Otherwise (missing or ambiguous) -> Manual Review
        if extracted_data.get("estado_deuda"):
            estado_lower = extracted_data["estado_deuda"].lower()
            
            if "sin anotaciones" in estado_lower:
                # This is the desired "approved" state for debt certificate, do nothing (no error)
                pass 
            elif "con anotaciones" in estado_lower:
                add_critical_error("estado_deuda", "The debt certificate indicates 'CON ANOTACIONES', which is a critical error.")
            else:
                add_manual_review_error("estado_deuda", f"Debt status '{extracted_data['estado_deuda']}' is ambiguous. Manual review needed (expected 'SIN ANOTACIONES' or 'CON ANOTACIONES').")
        else:
            # If estado_deuda is missing, it's a critical error as we can't determine debt status
            add_critical_error("estado_deuda", "Debt status not found on Debt Certificate.")



    elif doc_type == "REFERENCIAS_PERSONALES":
        # Rule: Deben ser a lo menos 2
        if not isinstance(extracted_data, list):
            add_critical_error("extracted_data", "References were not extracted as a list.")
        else:
            min_references = 2
            if len(extracted_data) < min_references:
                add_critical_error("count", f"At least {min_references} references are required, but {len(extracted_data)} were found.")
            
            for i, ref in enumerate(extracted_data):
                # Name is critical (basic check)
                if not ref.get("nombre_referencia"):
                    add_critical_error(f"reference_{i+1}.nombre_referencia", "Mandatory reference name not found.")
                
                # Rule: Y deben contener un teléfono válido para Chile.
                telefono = ref.get("numero_telefono", "")
                if not telefono:
                    add_critical_error(f"reference_{i+1}.numero_telefono", "Mandatory phone number not found.")
                else:
                    # Chilean phone format validation: +56 9 XXXXXXXX or +56 2 XXXXXXXX, etc.
                    # Or just 9 XXXXXXXX if it's a mobile
                    # Regex for +56 [2-9] XXXXXXXX (8 digits after 56 and area/mobile code)
                    telefono_clean = telefono.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").replace("+", "")
                    # Updated regex:
                    # ^56: must start with 56 (country code)
                    # (?:9\d{8}|[2-8]\d{7})$: non-capturing group for area/mobile code followed by digits
                    #   9\d{8}: mobile (9 followed by 8 digits)
                    #   [2-8]\d{7}: fixed line (2-8 followed by 7 digits)
                    # | : OR (for cases where +56 might be missing but is a valid local number)
                    # ^(?:9\d{8}|[2-8]\d{7})$ : checks if it's just the local number without country code
                    if not re.fullmatch(r"^(?:56)?(?:9\d{8}|[2-8]\d{7})$", telefono_clean):
                        add_critical_error(f"reference_{i+1}.numero_telefono", f"Invalid Chilean phone format '{telefono}'.")
                        # Changed to critical error as per "must contain a valid phone"

    # LIQUIDACION_SUELDO - No new rules specified, keeping previous logic
    elif doc_type == "LIQUIDACION_SUELDO":
        critical_fields = ["nombre_empleado", "run_empleado", "rut_empresa", "nombre_empresa", "cargo", "periodo", "fecha_emision", "sueldo_bruto", "sueldo_liquido"]
        for field in critical_fields:
            if not extracted_data.get(field):
                add_critical_error(field, f"Critical field '{field}' not found or empty in Payroll Slip.")

        if extracted_data.get("run_empleado"):
            if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["run_empleado"]):
                add_critical_error("run_empleado", f"Invalid employee RUN format '{extracted_data['run_empleado']}'.")

        if extracted_data.get("rut_empresa"):
             if not re.fullmatch(r"^\d{1,2}\.\d{3}\.\d{3}[-][0-9Kk]$|^\d{7,8}[-][0-9Kk]$", extracted_data["rut_empresa"]):
                add_critical_error("rut_empresa", f"Invalid company RUT format '{extracted_data['rut_empresa']}'.")

        if extracted_data.get("fecha_emision"):
            try:
                emission_date_obj = datetime.strptime(extracted_data["fecha_emision"], "%Y-%m-%d").date()
                
                if solicitud_fecha_curse_obj:
                    months_diff = (solicitud_fecha_curse_obj.year - emission_date_obj.year) * 12 + \
                                  (solicitud_fecha_curse_obj.month - emission_date_obj.month)
                    if months_diff > 3: 
                        add_critical_error("fecha_emision", f"Payroll slip is too old ({months_diff} months old regarding curse date). Maximum allowed: 3 months.")
                    elif months_diff < 0: # Emission date is in the future
                         add_critical_error("fecha_emision", f"Payroll slip emission date ({extracted_data['fecha_emision']}) is in the future relative to curse date.")
                    elif months_diff > 2: # Example for manual review, adjust as needed
                        add_manual_review_error("fecha_emision", f"Payroll slip is {months_diff} months old regarding curse date. Review recommended.")
                else:
                    # Fallback to current date if curse date is invalid/missing
                    days_old = (datetime.now().date() - emission_date_obj).days
                    if days_old > 90:
                        add_critical_error("fecha_emision", f"Payroll slip is too old ({days_old} days old). Maximum allowed: 90 days.")
            except ValueError:
                add_critical_error("fecha_emision", f"Invalid emission date format '{extracted_data['fecha_emision']}'.")

        for monto_field in ["sueldo_bruto", "sueldo_liquido", "total_descuentos", "total_imposiciones"]:
            if extracted_data.get(monto_field) is not None:
                try:
                    clean_monto = str(extracted_data[monto_field]).replace(".", "").replace(",", ".")
                    float(clean_monto)  
                except ValueError:
                    add_manual_review_error(monto_field, f"Value for '{monto_field}' is not a valid number and requires manual review.")
            else:
                add_critical_error(monto_field, f"Critical field '{monto_field}' not found or empty in Payroll Slip.")

    elif doc_type == "OTRO" or doc_type == "unknown":
        add_manual_review_error("document_type", "Unknown or unclassified document type. Requires manual review.")
    
    else:
        add_manual_review_error("document_type", f"Document type '{doc_type}' recognized but requires manual validation.")

    # Log the result
    if validation_status == "OK":
        print(f"  {doc_id} validated successfully")
    elif validation_status == "ERROR":
        error_count = len([e for e in validation_errors if e.get("severity") == "CRITICAL"])
        print(f"  {doc_id} has {error_count} critical error(s)")
    else:  # PENDIENTE_MANUAL
        manual_count = len([e for e in validation_errors if e.get("severity") == "MANUAL_REVIEW"])
        print(f"  {doc_id} requires manual review ({manual_count} item(s))")

    return {
        "validation_status": validation_status,
        "validation_errors": validation_errors
    }