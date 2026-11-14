
from django.db import transaction
from django.contrib.auth.models import User

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import ValidationError

from api.serializers import (
    RegisterSerializer,
    LoginSerializer,
    GoogleLoginSerializer,
    ComplaintSerializer,
    CustomerSerializer,
)

from api.permissions import (
    HasCompanyPermission,
    IsCompanyAdmin,
)

from api.models import (
    Customer,
    Complaint,
    Ticket,
    Company,
    Role,
    CompanyMembership,
)

from api.services.ticket_service import accept_complaint_and_create_ticket
from api.services.google_auth_service import (
    authenticate_google_user,
    GoogleAuthError,
)


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        try:
            company = Company.objects.get(slug="demo-company", is_active=True)
            customer_role = Role.objects.get(company=company, slug="customer")

        except (Company.DoesNotExist, Role.DoesNotExist):
            return Response(
                {"error": "Company or customer role not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        CompanyMembership.objects.update_or_create(
            user=user,
            company=company,
            defaults={"role": customer_role, "is_active": True},
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


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        user = User.objects.filter(email__iexact=email).first()

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

        serializer = ComplaintSerializer(data=request.data)

        if serializer.is_valid():
            complaint = serializer.save(
                company=membership.company,
                customer=customer,
            )

            return Response({
                "message": "Complaint submitted successfully",
                "complaint_id": complaint.id,
                "status": complaint.status,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

        return Response(list(complaints), status=status.HTTP_200_OK)


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
        ).values(
            "id",
            "ticket_number",
            "status",
            "created_at",
        )

        return Response(list(tickets), status=status.HTTP_200_OK)


# ADMIN APIs

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

        return Response(serializer.data, status=status.HTTP_200_OK)

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

            return Response(
                {
                    "message": "Customer created successfully.",
                    "customer": CustomerSerializer(customer).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )


class AdminComplaintListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        complaints = Complaint.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).select_related("customer").order_by("-created_at")

        data = [{
            "id": item.id,
            "subject": item.subject,
            "description": item.description,
            "status": item.status,
            "customer_id": item.customer.id,
            "customer_name": (
                f"{item.customer.first_name} {item.customer.last_name}"
            ),
            "created_at": item.created_at,
        } for item in complaints]

        return Response(data, status=status.HTTP_200_OK)


class AdminTicketListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, company_id):
        tickets = Ticket.objects.filter(
            company_id=company_id,
            company__is_active=True,
        ).select_related(
            "customer", "assigned_agent"
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

        return Response(data, status=status.HTTP_200_OK)
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
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, company_id, customer_id):
        return self.update_customer(
            request, company_id, customer_id, partial=False
        )

    def patch(self, request, company_id, customer_id):
        return self.update_customer(
            request, company_id, customer_id, partial=True
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
            "assigned_agent", "complaint"
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