from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from types import SimpleNamespace

from api.models import CompanyMembership, Role
from api.permissions import HasCompanyPermission, IsCompanyAdmin, IsCompanyMember
from api.services.authorization_service import assign_company_role, create_company_with_admin

User = get_user_model()


class CompanyAuthorizationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = User.objects.create_user(username="admin", password="test-pass-123")
        self.agent = User.objects.create_user(username="agent", password="test-pass-123")
        self.other = User.objects.create_user(username="other", password="test-pass-123")
        self.company = create_company_with_admin(
            name="Acme Support", slug="acme-support", admin_user=self.admin
        )
        self.agent_role = Role.objects.get(company=self.company, slug="agent")
        CompanyMembership.objects.create(
            user=self.agent, company=self.company, role=self.agent_role
        )

    def _request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def _view(self, company_id, required_permission=None):
        return SimpleNamespace(
            kwargs={"company_id": company_id},
            required_permission=required_permission,
        )

    def test_company_creation_creates_roles_and_admin_membership(self):
        membership = CompanyMembership.objects.get(user=self.admin, company=self.company)
        self.assertEqual(membership.role.slug, "company_admin")
        self.assertEqual(
            set(Role.objects.filter(company=self.company).values_list("slug", flat=True)),
            {"company_admin", "manager", "agent", "customer"},
        )

    def test_active_member_is_allowed(self):
        self.assertTrue(IsCompanyMember().has_permission(
            self._request(self.agent), self._view(self.company.id)
        ))

    def test_non_member_is_denied(self):
        self.assertFalse(IsCompanyMember().has_permission(
            self._request(self.other), self._view(self.company.id)
        ))

    def test_permission_code_is_enforced(self):
        self.assertTrue(HasCompanyPermission().has_permission(
            self._request(self.agent), self._view(self.company.id, "tickets.create")
        ))
        self.assertFalse(HasCompanyPermission().has_permission(
            self._request(self.agent), self._view(self.company.id, "members.manage")
        ))

    def test_company_admin_check(self):
        self.assertTrue(IsCompanyAdmin().has_permission(
            self._request(self.admin), self._view(self.company.id)
        ))
        self.assertFalse(IsCompanyAdmin().has_permission(
            self._request(self.agent), self._view(self.company.id)
        ))

    def test_member_assignment_requires_management_permission(self):
        new_user = User.objects.create_user(username="new-agent", password="test-pass-123")
        with self.assertRaises(Exception):
            assign_company_role(
                actor=self.agent, user=new_user,
                company_id=self.company.id, role_id=self.agent_role.id,
            )
        membership, created = assign_company_role(
            actor=self.admin, user=new_user,
            company_id=self.company.id, role_id=self.agent_role.id,
        )
        self.assertTrue(created)
        self.assertEqual(membership.role_id, self.agent_role.id)

    def test_role_from_another_company_cannot_be_assigned(self):
        another_company = create_company_with_admin(
            name="Other Co", slug="other-co", admin_user=self.other
        )
        other_role = Role.objects.get(company=another_company, slug="agent")
        with self.assertRaises(Exception):
            assign_company_role(
                actor=self.admin, user=self.other,
                company_id=self.company.id, role_id=other_role.id,
            )


from rest_framework.test import APIClient
from api.models import FAQCategory, FAQArticle, SLAPolicy, Notification, CompanySetting


class CompanyOnboardingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_company_registration_creates_admin_and_default_roles(self):
        response = self.client.post(
            "/api/auth/company/register/",
            {
                "company_name": "Onboarding Test Co",
                "username": "onboarding-admin",
                "email": "onboarding-admin@example.test",
                "password": "Strong-test-pass-123",
                "confirm_password": "Strong-test-pass-123",
                "first_name": "Onboarding",
                "last_name": "Admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        company_id = response.data["company"]["id"]
        membership = CompanyMembership.objects.get(
            user__username="onboarding-admin", company_id=company_id
        )
        self.assertEqual(membership.role.slug, "company_admin")
        self.assertEqual(
            set(Role.objects.filter(company_id=company_id).values_list("slug", flat=True)),
            {"company_admin", "manager", "agent", "customer"},
        )

    def test_customer_registration_joins_selected_company(self):
        admin = User.objects.create_user(
            username="tenant-admin", email="tenant-admin@example.test",
            password="Strong-test-pass-123",
        )
        company = create_company_with_admin(
            name="Customer Signup Co", slug="customer-signup-co", admin_user=admin
        )
        response = self.client.post(
            "/api/auth/register/",
            {
                "company_id": company.id,
                "username": "tenant-customer",
                "email": "tenant-customer@example.test",
                "password": "Strong-test-pass-123",
                "confirm_password": "Strong-test-pass-123",
                "first_name": "Tenant",
                "last_name": "Customer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        membership = CompanyMembership.objects.get(
            user__username="tenant-customer", company=company
        )
        self.assertEqual(membership.role.slug, "customer")

    def test_company_registration_rejects_duplicate_slug(self):
        admin = User.objects.create_user(
            username="existing-admin", email="existing-admin@example.test",
            password="Strong-test-pass-123",
        )
        create_company_with_admin(
            name="Existing Company", slug="existing-company", admin_user=admin
        )
        response = self.client.post(
            "/api/auth/company/register/",
            {
                "company_name": "Existing Company",
                "username": "another-admin",
                "email": "another-admin@example.test",
                "password": "Strong-test-pass-123",
                "confirm_password": "Strong-test-pass-123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)


class SupportPlatformAPITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="support-admin", email="support-admin@example.test",
            password="Strong-test-pass-123"
        )
        self.company = create_company_with_admin(
            name="Support Test Co", slug="support-test-co", admin_user=self.admin
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.base = f"/api/companies/{self.company.id}/"

    def test_faq_category_and_article_flow(self):
        response = self.client.post(
            self.base + "faq-categories/",
            {"name": "Accounts", "description": "Account help"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        category_id = response.data["id"]

        response = self.client.post(
            self.base + "faqs/",
            {
                "category": category_id,
                "question": "How do I reset my password?",
                "answer": "Use the password reset page.",
                "is_published": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.get(self.base + "faqs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_sla_policy_creation(self):
        response = self.client.post(
            self.base + "admin/sla-policies/",
            {
                "name": "Standard",
                "priority": "medium",
                "first_response_minutes": 60,
                "resolution_minutes": 480,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SLAPolicy.objects.filter(company=self.company).count(), 1)

    def test_company_settings_are_scoped_and_persisted(self):
        response = self.client.patch(
            self.base + "admin/settings/",
            {"business_hours": {"timezone": "Asia/Kolkata"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        setting = CompanySetting.objects.get(company=self.company, key="business_hours")
        self.assertEqual(setting.value["timezone"], "Asia/Kolkata")

        response = self.client.get(self.base + "admin/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["business_hours"]["timezone"], "Asia/Kolkata")

    def test_notification_list_only_returns_current_users_notifications(self):
        Notification.objects.create(
            company=self.company,
            recipient=self.admin,
            title="Test notification",
            body="Ticket updated",
            kind="ticket_status",
        )
        response = self.client.get(self.base + "notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        response = self.client.patch(
            self.base + "notifications/", {"ids": [response.data[0]["id"]]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Notification.objects.get(recipient=self.admin).is_read)


from django.core.files.uploadedfile import SimpleUploadedFile
from api.models import (
    Customer, TicketCategory, Complaint, Ticket, ConversationMessage,
    LiveChatSession, TicketFeedback,
)


class ConversationLiveChatAndFeedbackTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="module-admin", email="module-admin@example.test",
            password="Strong-test-pass-123"
        )
        self.customer_user = User.objects.create_user(
            username="module-customer", email="module-customer@example.test",
            password="Strong-test-pass-123"
        )
        self.agent = User.objects.create_user(
            username="module-agent", email="module-agent@example.test",
            password="Strong-test-pass-123"
        )
        self.company = create_company_with_admin(
            name="Module Test Co", slug="module-test-co", admin_user=self.admin
        )
        self.customer_role = Role.objects.get(company=self.company, slug="customer")
        self.agent_role = Role.objects.get(company=self.company, slug="agent")
        CompanyMembership.objects.create(user=self.customer_user, company=self.company, role=self.customer_role)
        CompanyMembership.objects.create(user=self.agent, company=self.company, role=self.agent_role)
        self.customer = Customer.objects.create(
            company=self.company, first_name="Module", last_name="Customer",
            email=self.customer_user.email,
        )
        self.category = TicketCategory.objects.create(company=self.company, name="General")
        complaint = Complaint.objects.create(
            company=self.company, customer=self.customer, category=self.category,
            subject="Test ticket", description="Test description", status="accepted",
        )
        self.ticket = Ticket.objects.create(
            company=self.company, complaint=complaint, customer=self.customer,
            assigned_agent=self.agent, ticket_number="TKT-TEST-MODULE-01",
        )
        self.client = APIClient()
        self.base = f"/api/companies/{self.company.id}/"

    def test_customer_agent_conversation_and_internal_note_visibility(self):
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post(
            self.base + f"tickets/{self.ticket.id}/messages/",
            {"message": "I need help"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        self.client.force_authenticate(user=self.agent)
        response = self.client.post(
            self.base + f"tickets/{self.ticket.id}/messages/",
            {"message": "Internal investigation note", "is_internal": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ConversationMessage.objects.filter(ticket=self.ticket).count(), 2)

        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get(self.base + f"tickets/{self.ticket.id}/messages/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertFalse(response.data[0]["is_internal"])

    def test_live_chat_customer_agent_flow(self):
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post(
            self.base + "live-chat/", {"subject": "Need assistance"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        session_id = response.data["id"]

        self.client.force_authenticate(user=self.agent)
        response = self.client.patch(self.base + f"live-chat/{session_id}/accept/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            self.base + f"live-chat/{session_id}/messages/",
            {"message": "Hello, how can I help?"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.patch(self.base + f"live-chat/{session_id}/end/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LiveChatSession.objects.get(pk=session_id).status, "ended")

    def test_customer_cannot_view_or_accept_agent_pending_complaints(self):
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get(self.base + "agent/complaints/")
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            self.base + "agent/complaints/accept/",
            {"complaint_id": self.ticket.complaint_id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_active_agent_can_view_pending_complaints(self):
        self.client.force_authenticate(user=self.agent)
        response = self.client.get(self.base + "agent/complaints/")
        self.assertEqual(response.status_code, 200)

    def test_feedback_requires_closed_ticket_and_one_rating(self):
        self.ticket.status = "closed"
        self.ticket.save(update_fields=["status"])
        self.client.force_authenticate(user=self.customer_user)
        url = self.base + f"tickets/{self.ticket.id}/feedback/"
        response = self.client.post(url, {"rating": 5, "comment": "Helpful"}, format="json")
        self.assertEqual(response.status_code, 201)
        response = self.client.post(url, {"rating": 4}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(TicketFeedback.objects.filter(ticket=self.ticket).count(), 1)
