def add_service_error(form, exc, field_by_code=None):
    """Attach a service-layer ApplicationError to the form field it concerns,
    so the UI can show it under that input. Errors that don't belong to any
    field (rate limits, expired links) stay form-wide."""
    field = (field_by_code or {}).get(exc.code)
    if field not in form.fields:
        field = None
    form.add_error(field, exc.message)
