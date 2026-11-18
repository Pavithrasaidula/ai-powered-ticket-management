import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from api.models import Complaint, Ticket, TicketStatusHistory
from api.services.platform_service import apply_sla_policy, notify_ticket_customer


@transaction.atomic
def accept_complaint_and_create_ticket(complaint_id, company_id, agent):
    complaint = Complaint.objects.select_for_update().filter(
        id=complaint_id, company_id=company_id
    ).first()
    if complaint is None:
        raise ValidationError("Complaint not found in this company.")
    if complaint.status != "pending":
        raise ValidationError("This complaint has already been processed.")

    ticket = Ticket.objects.create(
        company=complaint.company,
        complaint=complaint,
        customer=complaint.customer,
        assigned_agent=agent,
        ticket_number=f"TKT-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
    )
    TicketStatusHistory.objects.create(
        ticket=ticket, company=complaint.company, old_status="",
        new_status=ticket.status, changed_by=agent,
        note="Ticket created when the complaint was accepted.",
    )
    apply_sla_policy(ticket)
    notify_ticket_customer(
        ticket, "Your ticket has been created",
        f"Ticket {ticket.ticket_number} has been assigned to an agent.",
        "ticket_created",
    )
    complaint.status = "accepted"
    complaint.save(update_fields=["status", "updated_at"])
    return ticket


@transaction.atomic
def update_ticket_status(*, ticket, new_status, changed_by, note="", allow_close=False):
    current_status = ticket.status
    allowed_transitions = {
        "open": {"in_progress"},
        "in_progress": {"resolved"},
        "resolved": {"closed"} if allow_close else set(),
        "closed": set(),
    }
    if new_status == current_status:
        raise ValidationError({"status": "Ticket is already in this status."})
    if new_status not in allowed_transitions.get(current_status, set()):
        raise ValidationError({
            "status": f"Cannot change ticket status from '{current_status}' to '{new_status}'."
        })

    ticket.status = new_status
    ticket.save(update_fields=["status", "updated_at"])
    TicketStatusHistory.objects.create(
        ticket=ticket, company=ticket.company, old_status=current_status,
        new_status=new_status, changed_by=changed_by, note=note,
    )
    notify_ticket_customer(
        ticket, "Ticket status updated",
        f"Your ticket {ticket.ticket_number} is now {new_status}.",
        "ticket_status",
    )
    if new_status == "resolved" and hasattr(ticket, "sla"):
        ticket.sla.resolved_at = timezone.now()
        ticket.sla.save(update_fields=["resolved_at"])
    return ticket
