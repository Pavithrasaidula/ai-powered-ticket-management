
# =====================================================
# DJANGO IMPORTS
# =====================================================

from django.db import transaction
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
    Role,

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

from api.services.ticket_service import (
    accept_complaint_and_create_ticket,
    update_ticket_status,
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
# 2. USER REGISTRATION API
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
            company = Company.objects.get(
                slug="demo-company",
                is_active=True,
            )

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
