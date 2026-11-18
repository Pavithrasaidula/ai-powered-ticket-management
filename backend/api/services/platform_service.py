from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from api.models import (
    CompanyMembership, Notification, SLAPolicy, TicketSLA, AuditLog, Customer
)


def create_notification(*, company, recipient, title, body, kind="general", ticket=None):
    return Notification.objects.create(
        company=company, recipient=recipient, title=title, body=body,
        kind=kind, ticket=ticket
    )


def notify_ticket_customer(ticket, title, body, kind):
    User = get_user_model()
    customer_user = User.objects.filter(email__iexact=ticket.customer.email, is_active=True).first()
    if customer_user:
        create_notification(
            company=ticket.company, recipient=customer_user,
            title=title, body=body, kind=kind, ticket=ticket
        )


def apply_sla_policy(ticket):
    policy = SLAPolicy.objects.filter(
        company=ticket.company, is_active=True, priority="medium"
    ).order_by("id").first()
    if not policy:
        return None
    now = timezone.now()
    return TicketSLA.objects.update_or_create(
        ticket=ticket,
        defaults={
            "policy": policy,
            "response_due_at": now + timedelta(minutes=policy.first_response_minutes),
            "resolution_due_at": now + timedelta(minutes=policy.resolution_minutes),
        },
    )[0]


def write_audit(*, company, actor, action, resource_type, resource_id="", details=None, ip_address=None):
    return AuditLog.objects.create(
        company=company, actor=actor, action=action,
        resource_type=resource_type, resource_id=str(resource_id),
        details=details or {}, ip_address=ip_address,
    )
