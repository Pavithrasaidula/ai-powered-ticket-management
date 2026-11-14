
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from api.models import Complaint, Ticket


@transaction.atomic
def accept_complaint_and_create_ticket(complaint_id, company_id, agent):
    complaint = Complaint.objects.select_for_update().filter(
        id=complaint_id,
        company_id=company_id,
    ).first()

    if complaint is None:
        raise ValidationError("Complaint not found in this company.")

    if complaint.status != "pending":
        raise ValidationError("This complaint has already been processed.")

    ticket_number = (
        f"TKT-{timezone.localdate():%Y%m%d}-"
        f"{uuid.uuid4().hex[:8].upper()}"
    )

    ticket = Ticket.objects.create(
        company=complaint.company,
        complaint=complaint,
        customer=complaint.customer,
        assigned_agent=agent,
        ticket_number=ticket_number,
    )

    complaint.status = "accepted"
    complaint.save(update_fields=["status", "updated_at"])

    return ticket
