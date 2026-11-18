from django.db import transaction
from django.db.models import Count, Avg
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from api.models import (
    Company, CompanyMembership, Ticket, Customer, FAQCategory, FAQArticle,
    SLAPolicy, TicketSLA, Notification, LiveChatSession, LiveChatMessage,
    TicketFeedback, AuditLog, CompanySetting,
)


def membership_for(user, company_id):
    return CompanyMembership.objects.select_related("role", "company").filter(
        user=user, company_id=company_id, is_active=True, company__is_active=True
    ).first()


def admin_required(user, company_id):
    membership = membership_for(user, company_id)
    return membership if membership and membership.role.slug == "company_admin" else None


def audit(company_id, actor, action, resource_type, resource_id="", details=None, request=None):
    ip = request.META.get("REMOTE_ADDR") if request else None
    AuditLog.objects.create(
        company_id=company_id, actor=actor, action=action,
        resource_type=resource_type, resource_id=str(resource_id),
        details=details or {}, ip_address=ip,
    )


class FAQView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not membership_for(request.user, company_id):
            return Response({"error": "Active company membership required."}, status=403)
        qs = FAQArticle.objects.filter(company_id=company_id, is_published=True).select_related("category")
        return Response([{"id": x.id, "category": x.category.name, "question": x.question, "answer": x.answer} for x in qs])

    def post(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        question, answer = str(request.data.get("question", "")).strip(), str(request.data.get("answer", "")).strip()
        category_id = request.data.get("category")
        category = FAQCategory.objects.filter(id=category_id, company_id=company_id, is_active=True).first()
        if not question or not answer or not category:
            return Response({"error": "question, answer and a valid category are required."}, status=400)
        article = FAQArticle.objects.create(company_id=company_id, category=category, question=question, answer=answer, is_published=bool(request.data.get("is_published", False)), created_by=request.user)
        audit(company_id, request.user, "faq.created", "FAQArticle", article.id, request=request)
        return Response({"id": article.id, "question": article.question, "answer": article.answer, "is_published": article.is_published}, status=201)


class FAQCategoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not membership_for(request.user, company_id):
            return Response({"error": "Active company membership required."}, status=403)
        return Response(list(FAQCategory.objects.filter(company_id=company_id).values("id", "name", "description", "is_active")))

    def post(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response({"name": ["This field is required."]}, status=400)
        obj, created = FAQCategory.objects.get_or_create(company_id=company_id, name=name, defaults={"description": request.data.get("description", "")})
        if not created:
            return Response({"name": ["This category already exists."]}, status=400)
        return Response({"id": obj.id, "name": obj.name}, status=201)


class SLAPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        return Response(list(SLAPolicy.objects.filter(company_id=company_id).values()))

    def post(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        try:
            obj = SLAPolicy.objects.create(
                company_id=company_id, name=request.data["name"],
                priority=request.data.get("priority", "medium"),
                first_response_minutes=int(request.data.get("first_response_minutes", 240)),
                resolution_minutes=int(request.data.get("resolution_minutes", 1440)),
                is_active=bool(request.data.get("is_active", True)),
            )
        except (KeyError, TypeError, ValueError):
            return Response({"error": "Provide name and valid positive SLA minute values."}, status=400)
        if obj.first_response_minutes <= 0 or obj.resolution_minutes <= 0:
            obj.delete()
            return Response({"error": "SLA minutes must be greater than zero."}, status=400)
        audit(company_id, request.user, "sla_policy.created", "SLAPolicy", obj.id, request=request)
        return Response({"id": obj.id, "name": obj.name, "priority": obj.priority, "first_response_minutes": obj.first_response_minutes, "resolution_minutes": obj.resolution_minutes}, status=201)


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not membership_for(request.user, company_id):
            return Response({"error": "Active company membership required."}, status=403)
        qs = Notification.objects.filter(company_id=company_id, recipient=request.user)
        return Response(list(qs.values("id", "title", "body", "kind", "ticket_id", "is_read", "created_at")))

    def patch(self, request, company_id):
        if not membership_for(request.user, company_id):
            return Response({"error": "Active company membership required."}, status=403)
        ids = request.data.get("ids")
        qs = Notification.objects.filter(company_id=company_id, recipient=request.user)
        if ids is not None:
            if not isinstance(ids, list):
                return Response({"ids": ["Expected a list of notification IDs."]}, status=400)
            qs = qs.filter(id__in=ids)
        qs.update(is_read=True, read_at=timezone.now())
        return Response({"message": "Notifications marked as read.", "updated": qs.count()})


class LiveChatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        member = membership_for(request.user, company_id)
        if not member:
            return Response({"error": "Active company membership required."}, status=403)
        qs = LiveChatSession.objects.filter(company_id=company_id)
        if member.role.slug == "customer":
            qs = qs.filter(customer=request.user)
        elif member.role.slug == "agent":
            qs = qs.filter(assigned_agent=request.user) | qs.filter(status="waiting", assigned_agent__isnull=True)
        return Response(list(qs.values("id", "customer_id", "assigned_agent_id", "status", "subject", "started_at", "ended_at")))

    def post(self, request, company_id):
        member = membership_for(request.user, company_id)
        if not member or member.role.slug != "customer":
            return Response({"error": "Only an active company customer can start a live chat."}, status=403)
        session = LiveChatSession.objects.create(company_id=company_id, customer=request.user, subject=str(request.data.get("subject", ""))[:200])
        return Response({"id": session.id, "status": session.status}, status=201)


class LiveChatMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def get_session(self, request, company_id, session_id):
        member = membership_for(request.user, company_id)
        if not member:
            return None
        session = LiveChatSession.objects.filter(id=session_id, company_id=company_id).first()
        if not session:
            return None
        if member.role.slug == "customer" and session.customer_id != request.user.id:
            return None
        if member.role.slug == "agent" and session.assigned_agent_id not in (None, request.user.id):
            return None
        if member.role.slug not in ("customer", "agent", "company_admin"):
            return None
        return session

    def get(self, request, company_id, session_id):
        session = self.get_session(request, company_id, session_id)
        if not session:
            return Response({"error": "Chat session not found or access denied."}, status=404)
        return Response(list(session.messages.select_related("sender").values("id", "sender_id", "sender__username", "message", "created_at")))

    def post(self, request, company_id, session_id):
        session = self.get_session(request, company_id, session_id)
        if not session or session.status == "ended":
            return Response({"error": "Chat session not found, inaccessible or ended."}, status=404)
        message = str(request.data.get("message", "")).strip()
        if not message:
            return Response({"message": ["This field is required."]}, status=400)
        obj = LiveChatMessage.objects.create(session=session, sender=request.user, message=message)
        return Response({"id": obj.id, "message": obj.message, "created_at": obj.created_at}, status=201)


class LiveChatAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, company_id, session_id):
        member = membership_for(request.user, company_id)
        if not member or member.role.slug not in ("agent", "company_admin"):
            return Response({"error": "Agent or company administrator access required."}, status=403)
        session = LiveChatSession.objects.select_for_update().filter(id=session_id, company_id=company_id, status="waiting", assigned_agent__isnull=True).first()
        if not session:
            return Response({"error": "Waiting chat session not found."}, status=404)
        session.assigned_agent = request.user
        session.status = "active"
        session.save(update_fields=["assigned_agent", "status"])
        return Response({"id": session.id, "status": session.status, "assigned_agent_id": request.user.id})


class TicketFeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, company_id, ticket_id):
        member = membership_for(request.user, company_id)
        if not member or member.role.slug != "customer":
            return Response({"error": "Active customer membership required."}, status=403)
        ticket = Ticket.objects.select_related("customer").filter(id=ticket_id, company_id=company_id, customer__email__iexact=request.user.email, status__in=("resolved", "closed")).first()
        if not ticket:
            return Response({"error": "Only your resolved or closed tickets can be rated."}, status=404)
        try:
            rating = int(request.data.get("rating"))
        except (TypeError, ValueError):
            return Response({"rating": ["Provide an integer from 1 to 5."]}, status=400)
        if rating < 1 or rating > 5:
            return Response({"rating": ["Rating must be between 1 and 5."]}, status=400)
        obj, created = TicketFeedback.objects.get_or_create(ticket=ticket, defaults={"company_id": company_id, "customer": ticket.customer, "rating": rating, "comment": str(request.data.get("comment", ""))})
        if not created:
            return Response({"error": "Feedback has already been submitted for this ticket."}, status=409)
        audit(company_id, request.user, "ticket.feedback_submitted", "TicketFeedback", obj.id, {"rating": rating}, request)
        return Response({"id": obj.id, "rating": obj.rating, "comment": obj.comment}, status=201)


class CompanyReportsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        tickets = Ticket.objects.filter(company_id=company_id)
        return Response({
            "tickets": {
                "total": tickets.count(),
                "by_status": list(tickets.values("status").annotate(count=Count("id")).order_by("status")),
                "by_category": list(tickets.values("complaint__category__name").annotate(count=Count("id")).order_by("-count")),
            },
            "customers": Customer.objects.filter(company_id=company_id).count(),
            "feedback": {
                "count": TicketFeedback.objects.filter(company_id=company_id).count(),
                "average_rating": TicketFeedback.objects.filter(company_id=company_id).aggregate(value=Avg("rating"))["value"],
            },
            "live_chats": list(LiveChatSession.objects.filter(company_id=company_id).values("status").annotate(count=Count("id"))),
            "sla": {
                "tracked_tickets": TicketSLA.objects.filter(ticket__company_id=company_id).count(),
                "overdue_first_responses": TicketSLA.objects.filter(ticket__company_id=company_id, first_responded_at__isnull=True, response_due_at__lt=timezone.now()).count(),
                "overdue_resolutions": TicketSLA.objects.filter(ticket__company_id=company_id, resolved_at__isnull=True, resolution_due_at__lt=timezone.now()).count(),
            },
        })


class AuditLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        qs = AuditLog.objects.filter(company_id=company_id).select_related("actor")
        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        return Response([{"id": x.id, "actor": x.actor.username if x.actor else None, "action": x.action, "resource_type": x.resource_type, "resource_id": x.resource_id, "details": x.details, "ip_address": x.ip_address, "created_at": x.created_at} for x in qs[:500]])


class CompanySettingsView(APIView):
    permission_classes = [IsAuthenticated]
    ALLOWED_KEYS = {"company_profile", "business_hours", "notification_preferences", "ticket_preferences"}

    def get(self, request, company_id):
        if not membership_for(request.user, company_id):
            return Response({"error": "Active company membership required."}, status=403)
        return Response({x.key: x.value for x in CompanySetting.objects.filter(company_id=company_id)})

    def patch(self, request, company_id):
        if not admin_required(request.user, company_id):
            return Response({"error": "Company administrator access required."}, status=403)
        if not isinstance(request.data, dict) or not request.data:
            return Response({"error": "Provide a non-empty JSON object of settings."}, status=400)
        invalid = set(request.data.keys()) - self.ALLOWED_KEYS
        if invalid:
            return Response({"error": "Unsupported setting keys.", "invalid_keys": sorted(invalid)}, status=400)
        for key, value in request.data.items():
            obj, _ = CompanySetting.objects.update_or_create(company_id=company_id, key=key, defaults={"value": value, "updated_by": request.user})
            audit(company_id, request.user, "company_setting.updated", "CompanySetting", obj.id, {"key": key}, request)
        return Response({"message": "Company settings updated.", "settings": {x.key: x.value for x in CompanySetting.objects.filter(company_id=company_id)}})


class LiveChatEndView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, company_id, session_id):
        member = membership_for(request.user, company_id)
        if not member:
            return Response({"error": "Active company membership required."}, status=403)
        session = LiveChatSession.objects.filter(id=session_id, company_id=company_id).first()
        if not session:
            return Response({"error": "Chat session not found."}, status=404)
        allowed = (
            (member.role.slug == "customer" and session.customer_id == request.user.id)
            or (member.role.slug == "agent" and session.assigned_agent_id == request.user.id)
            or member.role.slug == "company_admin"
        )
        if not allowed:
            return Response({"error": "You cannot end this chat session."}, status=403)
        if session.status == "ended":
            return Response({"message": "Chat session is already ended.", "status": session.status})
        session.status = "ended"
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])
        audit(company_id, request.user, "live_chat.ended", "LiveChatSession", session.id, request=request)
        return Response({"message": "Chat session ended.", "status": session.status})
