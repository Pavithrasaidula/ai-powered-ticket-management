
# =====================================================
# DJANGO IMPORTS
# =====================================================

from django.db import transaction
from django.db.models import Count, Avg
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.models import User


# =====================================================
# DJANGO REST FRAMEWORK IMPORTS
# =====================================================

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser


# =====================================================
# PROJECT MODEL IMPORTS
# =====================================================

from api.models import (
    Company,
    CompanyMembership,
    Customer,
    Complaint,
    Ticket,
    TicketCategory,
    TicketStatusHistory,
    ConversationMessage,
    ConversationAttachment,
    Role,
    FAQCategory,
    FAQArticle,
    SLAPolicy,
    TicketSLA,
    Notification,
    LiveChatSession,
    LiveChatMessage,
    TicketFeedback,
    AuditLog,
    CompanySetting,
)


# =====================================================
# PROJECT SERIALIZER IMPORTS
# =====================================================

from api.serializers import (
    RegisterSerializer,
    LoginSerializer,
    GoogleLoginSerializer,
    ComplaintSerializer,
    CustomerSerializer,
    AgentCreateSerializer,
    AgentUpdateSerializer,
    TicketCategorySerializer,
    TicketAssignmentSerializer,
    TicketStatusUpdateSerializer,
)


# =====================================================
# PERMISSION IMPORTS
# =====================================================

from api.permissions import (
    HasCompanyPermission,
    IsCompanyAdmin,
)


# =====================================================
# SERVICE IMPORTS
# =====================================================

from api.services.authorization_service import create_company_with_admin

from api.services.ticket_service import (
    accept_complaint_and_create_ticket,
    update_ticket_status,
)

from api.services.platform_service import (
    write_audit, notify_ticket_customer, create_notification
)

from api.services.google_auth_service import (
    authenticate_google_user,
    GoogleAuthError,
)


# =====================================================
# 1. GOOGLE LOGIN API
# =====================================================

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        google_token = serializer.validated_data["id_token"]

        try:
            user, created = authenticate_google_user(google_token)
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Google login successful",
                "user_created": created,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            }, status=status.HTTP_200_OK)

        except GoogleAuthError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )


# =====================================================
# 2. COMPANY REGISTRATION API
# =====================================================

class CompanyRegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        company_name = str(request.data.get("company_name", "")).strip()
        requested_slug = str(request.data.get("company_slug", "")).strip()
        slug = slugify(requested_slug or company_name)

        if not company_name:
            return Response(
                {"company_name": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(company_name) > 150 or not slug or len(slug) > 160:
            return Response(
                {"error": "Provide a valid company name and company slug."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Company.objects.filter(slug=slug).exists():
            return Response(
                {"company_slug": ["This company URL is already registered."]},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        admin_user = serializer.save()
        company = create_company_with_admin(
            name=company_name,
            slug=slug,
            admin_user=admin_user,
        )
        audit(
            company.id, admin_user, "company.created", "Company",
            company.id, {"slug": company.slug}, request,
        )
        return Response({
            "message": "Company registered successfully. Please log in to continue.",
            "company": {
                "id": company.id,
                "name": company.name,
                "slug": company.slug,
            },
            "admin": {
                "id": admin_user.id,
                "username": admin_user.username,
                "email": admin_user.email,
                "role": "company_admin",
            },
        }, status=status.HTTP_201_CREATED)


# =====================================================
# 3. CUSTOMER REGISTRATION API
# =====================================================

class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            company_id = request.data.get("company_id")
            companies = Company.objects.filter(is_active=True)
            if company_id not in (None, ""):
                company = companies.get(id=company_id)
            else:
                # Backward compatibility for installations that still use demo-company.
                company = companies.get(slug="demo-company")

            customer_role = Role.objects.get(
                company=company,
                slug="customer",
            )

        except (Company.DoesNotExist, Role.DoesNotExist):
            return Response(
                {"error": "Company or customer role not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()

        CompanyMembership.objects.update_or_create(
            user=user,
            company=company,
            defaults={
                "role": customer_role,
                "is_active": True,
            },
        )

        Customer.objects.get_or_create(
            company=company,
            email=user.email,
            defaults={
                "first_name": user.first_name or user.username,
                "last_name": user.last_name or "Customer",
            },
        )

        return Response({
            "message": "Registration successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
            "company": company.name,
            "role": "customer",
        }, status=status.HTTP_201_CREATED)


# =====================================================
# 3. USER LOGIN API
# =====================================================

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = User.objects.filter(
            email__iexact=email,
        ).first()

        if user is None or not user.check_password(password):
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
        }, status=status.HTTP_200_OK)


# =====================================================
# 4. CUSTOMER COMPLAINT CREATION API
# =====================================================

class CustomerComplaintCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, company_id):
        membership = CompanyMembership.objects.filter(
            user=request.user,
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="customer",
        ).select_related("company").first()

        if membership is None:
            return Response(
                {"error": "You are not an active customer of this company."},
                status=status.HTTP_403_FORBIDDEN,
            )

        customer = Customer.objects.filter(
            company_id=company_id,
            email__iexact=request.user.email,
            is_active=True,
        ).first()

        if customer is None:
            return Response(
                {"error": "Customer record not found for this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ComplaintSerializer(
            data=request.data,
            context={"company_id": company_id},
        )

        if serializer.is_valid():
            complaint = serializer.save(
                company=membership.company,
                customer=customer,
            )

            return Response({
                "message": "Complaint submitted successfully",
                "complaint_id": complaint.id,
                "category": {
                    "id": complaint.category.id,
                    "name": complaint.category.name,
                },
                "status": complaint.status,
            }, status=status.HTTP_201_CREATED)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


# =====================================================
# 5. AGENT PENDING COMPLAINTS API
# =====================================================

class AgentPendingComplaintsView(APIView):
    permission_classes = [IsAuthenticated, HasCompanyPermission]
    required_permission = "tickets.view"

    def get(self, request, company_id):
        membership = CompanyMembership.objects.select_related("role").filter(
            user=request.user,
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="agent",
        ).first()
        if membership is None:
            return Response(
                {"error": "Active agent membership is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        complaints = Complaint.objects.filter(
            company_id=company_id,
            company__is_active=True,
            status="pending",
        ).values(
            "id",
            "subject",
            "description",
            "customer__first_name",
            "customer__last_name",
            "created_at",
        )

        return Response(
            list(complaints),
            status=status.HTTP_200_OK,
        )


# =====================================================
# 6. AGENT ACCEPT COMPLAINT API
# =====================================================

class AgentAcceptComplaintView(APIView):
    permission_classes = [IsAuthenticated, HasCompanyPermission]
    required_permission = "tickets.create"

    def post(self, request, company_id):
        membership = CompanyMembership.objects.select_related("role").filter(
            user=request.user,
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="agent",
        ).first()
        if membership is None:
            return Response(
                {"error": "Active agent membership is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        complaint_id = request.data.get("complaint_id")

        if not complaint_id:
            return Response(
                {"error": "complaint_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            complaint_id = int(complaint_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "complaint_id must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ticket = accept_complaint_and_create_ticket(
                complaint_id=complaint_id,
                company_id=company_id,
                agent=request.user,
            )

        except ValidationError as error:
            return Response(
                {"error": error.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "ticket_id": ticket.id,
            "ticket_number": ticket.ticket_number,
        }, status=status.HTTP_201_CREATED)


# =====================================================
# 7. CUSTOMER TICKET LIST API
# =====================================================

class CustomerTicketListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        membership = CompanyMembership.objects.filter(
            user=request.user,
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="customer",
        ).first()

        if membership is None:
            return Response(
                {"error": "You are not an active customer of this company."},
                status=status.HTTP_403_FORBIDDEN,
            )

        customer = Customer.objects.filter(
            company_id=company_id,
            email__iexact=request.user.email,
            is_active=True,
        ).first()

        if customer is None:
            return Response(
                {"error": "Customer record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        tickets = Ticket.objects.filter(
            company_id=company_id,
            customer=customer,
        ).prefetch_related("status_history__changed_by").order_by("-created_at")

        data = []
        for ticket in tickets:
            data.append({
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "status": ticket.status,
                "created_at": ticket.created_at,
                "status_history": [{
                    "old_status": item.old_status or None,
                    "new_status": item.new_status,
                    "note": item.note,
                    "changed_by": (
                        item.changed_by.username if item.changed_by else None
                    ),
                    "changed_at": item.created_at,
                } for item in ticket.status_history.all()],
            })

        return Response(data, status=status.HTTP_200_OK)


# =====================================================
# 8. ADMIN AGENT LIST AND CREATE API
# =====================================================

class AdminAgentListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        agents = CompanyMembership.objects.filter(
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="agent",
        ).select_related("user", "role")

        data = [{
            "user_id": item.user.id,
            "username": item.user.username,
            "email": item.user.email,
            "first_name": item.user.first_name,
            "last_name": item.user.last_name,
            "role": item.role.name,
            "is_active": item.is_active,
        } for item in agents]

        return Response(data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, company_id):
        company = Company.objects.filter(
            id=company_id,
            is_active=True,
        ).first()

        if company is None:
            return Response(
                {"error": "Active company not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        agent_role = Role.objects.filter(
            company=company,
            slug="agent",
        ).first()

        if agent_role is None:
            return Response(
                {"error": "Agent role not found for this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AgentCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated_data = serializer.validated_data

        password = validated_data.pop("password")
        validated_data.pop("confirm_password")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=password,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )

        membership = CompanyMembership.objects.create(
            user=user,
            company=company,
            role=agent_role,
            is_active=True,
        )

        return Response({
            "message": "Agent created successfully.",
            "agent": {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": membership.role.name,
                "company_id": company.id,
                "is_active": membership.is_active,
            },
        }, status=status.HTTP_201_CREATED)


# =====================================================
# 9. ADMIN AGENT DETAIL, UPDATE AND STATUS API
# =====================================================

class AdminAgentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get_agent(self, company_id, agent_id):
        return CompanyMembership.objects.filter(
            user_id=agent_id,
            company_id=company_id,
            company__is_active=True,
            role__slug="agent",
        ).select_related("user", "role").first()

    def get(self, request, company_id, agent_id):
        membership = self.get_agent(company_id, agent_id)

        if membership is None:
            return Response(
                {"error": "Agent not found in this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "user_id": membership.user.id,
            "username": membership.user.username,
            "email": membership.user.email,
            "first_name": membership.user.first_name,
            "last_name": membership.user.last_name,
            "role": membership.role.name,
            "company_id": company_id,
            "is_active": membership.is_active,
        }, status=status.HTTP_200_OK)

    def put(self, request, company_id, agent_id):
        return self.update_agent(
            request,
            company_id,
            agent_id,
            partial=False,
        )

    def patch(self, request, company_id, agent_id):
        if "is_active" in request.data:
            membership = self.get_agent(company_id, agent_id)

            if membership is None:
                return Response(
                    {"error": "Agent not found in this company."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            is_active = request.data["is_active"]

            if not isinstance(is_active, bool):
                return Response(
                    {"error": "is_active must be true or false."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership.is_active = is_active
            membership.save(update_fields=["is_active"])

            return Response({
                "message": (
                    "Agent activated successfully."
                    if is_active
                    else "Agent deactivated successfully."
                ),
                "user_id": membership.user.id,
                "username": membership.user.username,
                "is_active": membership.is_active,
            }, status=status.HTTP_200_OK)

        return self.update_agent(
            request,
            company_id,
            agent_id,
            partial=True,
        )

    def update_agent(self, request, company_id, agent_id, partial):
        membership = self.get_agent(company_id, agent_id)

        if membership is None:
            return Response(
                {"error": "Agent not found in this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AgentUpdateSerializer(
            membership.user,
            data=request.data,
            partial=partial,
            context={"user": membership.user},
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field, value in serializer.validated_data.items():
            setattr(membership.user, field, value)

        membership.user.save()

        return Response({
            "message": "Agent updated successfully.",
            "agent": {
                "user_id": membership.user.id,
                "username": membership.user.username,
                "email": membership.user.email,
                "first_name": membership.user.first_name,
                "last_name": membership.user.last_name,
                "role": membership.role.name,
                "company_id": company_id,
                "is_active": membership.is_active,
            },
        }, status=status.HTTP_200_OK)


# =====================================================
# 10. ADMIN CUSTOMER LIST AND CREATE API
# =====================================================

class AdminCustomerListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        customers = Customer.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).order_by("-created_at")

        serializer = CustomerSerializer(
            customers,
            many=True,
            context={"company_id": company_id},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, company_id):
        if not Company.objects.filter(
            id=company_id,
            is_active=True,
        ).exists():
            return Response(
                {"error": "Active company not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CustomerSerializer(
            data=request.data,
            context={"company_id": company_id},
        )

        if serializer.is_valid():
            customer = serializer.save(company_id=company_id)

            return Response({
                "message": "Customer created successfully.",
                "customer": CustomerSerializer(customer).data,
            }, status=status.HTTP_201_CREATED)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


# =====================================================
# 11. ADMIN CUSTOMER DETAIL AND UPDATE API
# =====================================================

class AdminCustomerDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get_customer(self, company_id, customer_id):
        return Customer.objects.filter(
            id=customer_id,
            company_id=company_id,
            company__is_active=True,
        ).first()

    def get(self, request, company_id, customer_id):
        customer = self.get_customer(company_id, customer_id)

        if customer is None:
            return Response(
                {"error": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CustomerSerializer(customer)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, company_id, customer_id):
        return self.update_customer(
            request,
            company_id,
            customer_id,
            partial=False,
        )

    def patch(self, request, company_id, customer_id):
        return self.update_customer(
            request,
            company_id,
            customer_id,
            partial=True,
        )

    def update_customer(self, request, company_id, customer_id, partial):
        customer = self.get_customer(company_id, customer_id)

        if customer is None:
            return Response(
                {"error": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CustomerSerializer(
            customer,
            data=request.data,
            partial=partial,
            context={"company_id": company_id},
        )

        if serializer.is_valid():
            serializer.save()

            return Response({
                "message": "Customer updated successfully.",
                "customer": serializer.data,
            }, status=status.HTTP_200_OK)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


# =====================================================
# 12. ADMIN CUSTOMER HISTORY API
# =====================================================

class AdminCustomerHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id, customer_id):
        customer = Customer.objects.filter(
            id=customer_id,
            company_id=company_id,
            company__is_active=True,
        ).first()

        if customer is None:
            return Response(
                {"error": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        complaints = Complaint.objects.filter(
            company_id=company_id,
            customer=customer,
        ).order_by("-created_at")

        tickets = Ticket.objects.filter(
            company_id=company_id,
            customer=customer,
        ).select_related(
            "assigned_agent",
            "complaint",
        ).order_by("-created_at")

        complaint_data = [{
            "id": item.id,
            "subject": item.subject,
            "description": item.description,
            "status": item.status,
            "created_at": item.created_at,
        } for item in complaints]

        ticket_data = [{
            "id": item.id,
            "ticket_number": item.ticket_number,
            "status": item.status,
            "assigned_agent": item.assigned_agent.username,
            "complaint_id": item.complaint_id,
            "created_at": item.created_at,
        } for item in tickets]

        return Response({
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}",
                "email": customer.email,
                "is_active": customer.is_active,
            },
            "total_complaints": len(complaint_data),
            "total_tickets": len(ticket_data),
            "complaints": complaint_data,
            "tickets": ticket_data,
        }, status=status.HTTP_200_OK)


# =====================================================
# 13. ADMIN COMPLAINT LIST API
# =====================================================

class AdminComplaintListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        complaints = Complaint.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).select_related(
            "customer",
            "category",
        ).order_by("-created_at")

        data = [{
            "id": item.id,
            "subject": item.subject,
            "description": item.description,
            "status": item.status,
            "customer_id": item.customer.id,
            "customer_name": (
                f"{item.customer.first_name} {item.customer.last_name}"
            ),
            "category_id": item.category_id,
            "category_name": (
                item.category.name if item.category else None
            ),
            "created_at": item.created_at,
        } for item in complaints]

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


# =====================================================
# 14. ADMIN TICKET LIST API
# =====================================================

class AdminTicketListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        tickets = Ticket.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).select_related(
            "customer",
            "assigned_agent",
        ).prefetch_related(
            "status_history__changed_by",
        ).order_by("-created_at")

        data = [{
            "id": item.id,
            "ticket_number": item.ticket_number,
            "status": item.status,
            "customer_id": item.customer.id,
            "customer_name": (
                f"{item.customer.first_name} {item.customer.last_name}"
            ),
            "assigned_agent_id": item.assigned_agent.id,
            "assigned_agent": item.assigned_agent.username,
            "created_at": item.created_at,
            "status_history": [{
                "old_status": history.old_status or None,
                "new_status": history.new_status,
                "note": history.note,
                "changed_by": (
                    history.changed_by.username if history.changed_by else None
                ),
                "changed_at": history.created_at,
            } for history in item.status_history.all()],
        } for item in tickets]

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


# =====================================================
# 15. ADMIN TICKET CATEGORY LIST AND CREATE API
# =====================================================

class AdminTicketCategoryListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        categories = TicketCategory.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).order_by("name")

        serializer = TicketCategorySerializer(
            categories,
            many=True,
            context={"company_id": company_id},
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, company_id):
        company = Company.objects.filter(
            id=company_id,
            is_active=True,
        ).first()

        if company is None:
            return Response(
                {"error": "Active company not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketCategorySerializer(
            data=request.data,
            context={"company_id": company_id},
        )

        if serializer.is_valid():
            category = serializer.save(company=company)

            return Response({
                "message": "Ticket category created successfully.",
                "category": TicketCategorySerializer(category).data,
            }, status=status.HTTP_201_CREATED)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


# =====================================================
# 16. ADMIN TICKET CATEGORY DETAIL AND UPDATE API
# =====================================================

class AdminTicketCategoryDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get_category(self, company_id, category_id):
        return TicketCategory.objects.filter(
            id=category_id,
            company_id=company_id,
            company__is_active=True,
        ).first()

    def get(self, request, company_id, category_id):
        category = self.get_category(company_id, category_id)

        if category is None:
            return Response(
                {"error": "Ticket category not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketCategorySerializer(category)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, company_id, category_id):
        return self.update_category(
            request,
            company_id,
            category_id,
            partial=False,
        )

    def patch(self, request, company_id, category_id):
        return self.update_category(
            request,
            company_id,
            category_id,
            partial=True,
        )

    def update_category(self, request, company_id, category_id, partial):
        category = self.get_category(company_id, category_id)

        if category is None:
            return Response(
                {"error": "Ticket category not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketCategorySerializer(
            category,
            data=request.data,
            partial=partial,
            context={"company_id": company_id},
        )

        if serializer.is_valid():
            serializer.save()

            message = "Ticket category updated successfully."

            if "is_active" in serializer.validated_data:
                if serializer.validated_data["is_active"]:
                    message = "Ticket category activated successfully."
                else:
                    message = "Ticket category deactivated successfully."

            return Response({
                "message": message,
                "category": serializer.data,
            }, status=status.HTTP_200_OK)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

# =====================================================
# 17. ADMIN TICKET ASSIGNMENT AND REASSIGNMENT API
# =====================================================

class AdminTicketAssignmentView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    @transaction.atomic
    def patch(self, request, company_id, ticket_id):

        # Find ticket inside the requested company
        ticket = Ticket.objects.select_for_update().filter(
            id=ticket_id,
            company_id=company_id,
            company__is_active=True,
        ).first()

        if ticket is None:
            return Response(
                {"error": "Ticket not found in this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate the selected agent
        serializer = TicketAssignmentSerializer(
            data=request.data,
            context={"company_id": company_id},
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_agent = serializer.validated_data["assigned_agent"]

        old_agent_id = ticket.assigned_agent_id

        # Update ticket assignment
        ticket.assigned_agent = new_agent
        ticket.save(update_fields=[
            "assigned_agent",
            "updated_at",
        ])
        write_audit(
            company=ticket.company, actor=request.user,
            action="ticket.assigned" if old_agent_id is None else "ticket.reassigned",
            resource_type="Ticket", resource_id=ticket.id,
            details={"previous_agent_id": old_agent_id, "assigned_agent_id": new_agent.id},
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        create_notification(
            company=ticket.company, recipient=new_agent,
            title="Ticket assigned",
            body=f"Ticket {ticket.ticket_number} has been assigned to you.",
            kind="ticket_assigned", ticket=ticket,
        )

        if old_agent_id == new_agent.id:
            message = "This ticket is already assigned to this agent."
        else:
            message = "Ticket assigned successfully."

        return Response({
            "message": message,
            "ticket": {
                "id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "status": ticket.status,
                "previous_agent_id": old_agent_id,
                "assigned_agent_id": new_agent.id,
                "assigned_agent": new_agent.username,
            },
        }, status=status.HTTP_200_OK)



# =====================================================
# 18. AGENT TICKET STATUS UPDATE API
# =====================================================

class AgentTicketStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated, HasCompanyPermission]
    required_permission = "tickets.update"

    @transaction.atomic
    def patch(self, request, company_id, ticket_id):
        membership = CompanyMembership.objects.filter(
            user=request.user,
            company_id=company_id,
            company__is_active=True,
            is_active=True,
            role__slug="agent",
        ).first()

        if membership is None:
            return Response(
                {"error": "Active agent membership is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ticket = Ticket.objects.select_for_update().filter(
            id=ticket_id,
            company_id=company_id,
            company__is_active=True,
            assigned_agent=request.user,
        ).first()

        if ticket is None:
            return Response(
                {"error": "Assigned ticket not found in this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = update_ticket_status(
                ticket=ticket,
                new_status=serializer.validated_data["status"],
                changed_by=request.user,
                note=serializer.validated_data.get("note", ""),
                allow_close=False,
            )
        except ValidationError as error:
            return Response(error.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Ticket status updated successfully.",
            "ticket_id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
        }, status=status.HTTP_200_OK)


# =====================================================
# 19. ADMIN TICKET STATUS UPDATE API
# =====================================================

class AdminTicketStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    @transaction.atomic
    def patch(self, request, company_id, ticket_id):
        ticket = Ticket.objects.select_for_update().filter(
            id=ticket_id,
            company_id=company_id,
            company__is_active=True,
        ).first()

        if ticket is None:
            return Response(
                {"error": "Ticket not found in this company."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = update_ticket_status(
                ticket=ticket,
                new_status=serializer.validated_data["status"],
                changed_by=request.user,
                note=serializer.validated_data.get("note", ""),
                allow_close=True,
            )
        except ValidationError as error:
            return Response(error.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": "Ticket status updated successfully.",
            "ticket_id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "status": ticket.status,
        }, status=status.HTTP_200_OK)



# =====================================================
# 20. TICKET CONVERSATIONS AND ATTACHMENTS
# =====================================================

class TicketConversationView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_access(self, request, company_id, ticket_id):
        ticket = Ticket.objects.select_related("customer", "assigned_agent").filter(
            id=ticket_id, company_id=company_id, company__is_active=True
        ).first()
        if ticket is None:
            return None, False, False

        membership = CompanyMembership.objects.select_related("role").filter(
            user=request.user, company_id=company_id, is_active=True,
            company__is_active=True
        ).first()
        if membership is None:
            return None, False, False

        role = membership.role.slug
        is_admin = role == "company_admin"
        is_agent = role == "agent" and ticket.assigned_agent_id == request.user.id
        is_customer = (
            role == "customer"
            and ticket.customer.email.lower() == (request.user.email or "").lower()
        )
        if not (is_admin or is_agent or is_customer):
            return None, False, False
        return ticket, is_customer, (is_admin or is_agent)

    def serialize_message(self, message):
        return {
            "id": message.id,
            "ticket_id": message.ticket_id,
            "sender": {
                "id": message.sender_id,
                "username": message.sender.username,
            },
            "message": message.message,
            "is_internal": message.is_internal,
            "created_at": message.created_at,
            "attachments": [
                {
                    "id": item.id,
                    "name": item.original_name,
                    "content_type": item.content_type,
                    "size": item.size,
                    "url": item.file.url if item.file else None,
                }
                for item in message.attachments.all()
            ],
        }

    def get(self, request, company_id, ticket_id):
        ticket, is_customer, staff = self.get_access(request, company_id, ticket_id)
        if ticket is None:
            return Response(
                {"error": "Ticket not found or you do not have access."},
                status=status.HTTP_404_NOT_FOUND,
            )
        messages = ticket.conversation_messages.select_related("sender").prefetch_related(
            "attachments"
        )
        if is_customer:
            messages = messages.filter(is_internal=False)
        return Response(
            [self.serialize_message(item) for item in messages],
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request, company_id, ticket_id):
        ticket, is_customer, staff = self.get_access(request, company_id, ticket_id)
        if ticket is None:
            return Response(
                {"error": "Ticket not found or you do not have access."},
                status=status.HTTP_404_NOT_FOUND,
            )

        message_text = str(request.data.get("message", "")).strip()
        if not message_text:
            return Response(
                {"message": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_internal = str(request.data.get("is_internal", "false")).lower() in (
            "true", "1", "yes"
        )
        if is_internal and not staff:
            return Response(
                {"error": "Only assigned agents and company admins can create internal notes."},
                status=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("attachments")
        if len(files) > 5:
            return Response(
                {"error": "You can attach a maximum of 5 files per message."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        import os
        allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".doc", ".docx", ".xlsx"}
        for uploaded in files:
            if uploaded.size > 10 * 1024 * 1024:
                return Response(
                    {"error": f"{uploaded.name} exceeds the 10 MB file limit."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            extension = os.path.splitext(uploaded.name)[1].lower()
            if extension not in allowed_extensions:
                return Response(
                    {"error": f"File type {extension or 'unknown'} is not allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        message = ConversationMessage.objects.create(
            company_id=company_id,
            ticket=ticket,
            sender=request.user,
            message=message_text,
            is_internal=is_internal,
        )
        for uploaded in files:
            ConversationAttachment.objects.create(
                company_id=company_id,
                message=message,
                file=uploaded,
                original_name=uploaded.name[:255],
                content_type=getattr(uploaded, "content_type", "")[:120],
                size=uploaded.size,
            )

        if not is_internal:
            if staff:
                notify_ticket_customer(
                    ticket, "New reply on your ticket",
                    f"An agent replied to ticket {ticket.ticket_number}.",
                    "ticket_message",
                )
            else:
                create_notification(
                    company=ticket.company, recipient=ticket.assigned_agent,
                    title="New customer reply",
                    body=f"The customer replied to ticket {ticket.ticket_number}.",
                    kind="ticket_message", ticket=ticket,
                )
        write_audit(
            company=ticket.company, actor=request.user,
            action="ticket.internal_note_added" if is_internal else "ticket.message_added",
            resource_type="ConversationMessage", resource_id=message.id,
            details={"ticket_id": ticket.id, "attachment_count": len(files)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        # The first staff reply satisfies the first-response SLA clock.
        if staff and hasattr(ticket, "sla") and ticket.sla.first_responded_at is None:
            from django.utils import timezone
            ticket.sla.first_responded_at = timezone.now()
            ticket.sla.save(update_fields=["first_responded_at"])

        message = ConversationMessage.objects.select_related("sender").prefetch_related(
            "attachments"
        ).get(pk=message.pk)
        return Response(
            {
                "message": "Conversation message created successfully.",
                "data": self.serialize_message(message),
            },
            status=status.HTTP_201_CREATED,
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
