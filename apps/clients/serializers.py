from apps.clients.services import compute_status


def serialize_client(client):
    status = compute_status(client)
    return {
        "id": client.pk,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "note": client.note,
        "active_requests": client.active_requests,
        "missing_documents": client.missing_items,
        "last_activity": client.last_activity.isoformat()
        if client.last_activity
        else None,
        "status": {"code": status.value, "label": status.label},
        "created_at": client.created_at.isoformat(),
    }
