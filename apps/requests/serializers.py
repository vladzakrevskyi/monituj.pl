from apps.requests.services import compute_status


def serialize_request(request_obj):
    status = compute_status(request_obj)
    return {
        "id": request_obj.pk,
        "name": request_obj.name,
        "description": request_obj.description,
        "client": {"id": request_obj.client_id, "name": request_obj.client.name},
        "deadline": request_obj.deadline.isoformat() if request_obj.deadline else None,
        "public_token": request_obj.public_token,
        "is_password_protected": request_obj.is_password_protected,
        "total_items": request_obj.total_items,
        "delivered_items": request_obj.delivered_items,
        "status": {"code": status.value, "label": status.label},
        "created_at": request_obj.created_at.isoformat(),
    }


def serialize_request_item(item):
    return {
        "id": item.pk,
        "name": item.name,
        "status": {"code": item.status, "label": item.get_status_display()},
        "rejection_reason": item.rejection_reason,
    }


def serialize_public_request(request_obj, items):
    status = compute_status(request_obj)
    return {
        "name": request_obj.name,
        "description": request_obj.description,
        "deadline": request_obj.deadline.isoformat() if request_obj.deadline else None,
        "status": {"code": status.value, "label": status.label},
        "total_items": request_obj.total_items,
        "delivered_items": request_obj.delivered_items,
        "items": [serialize_request_item(item) for item in items],
    }
