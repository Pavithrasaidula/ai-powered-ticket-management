
from django.urls import path

from rest_framework_simplejwt.views import TokenRefreshView

from api.views import (
    GoogleLoginView,
    RegisterView,
    LoginView,

    # Customer APIs
    CustomerComplaintCreateView,
    CustomerTicketListView,

    # Agent APIs
    AgentPendingComplaintsView,
    AgentAcceptComplaintView,

    # Admin Agent APIs
    AdminAgentListView,
    AdminAgentDetailView,

    # Admin Customer APIs
    AdminCustomerListView,
    AdminCustomerDetailView,
    AdminCustomerHistoryView,

    # Admin Complaint and Ticket APIs
    AdminComplaintListView,
    AdminTicketListView,
    AdminTicketAssignmentView,
    AgentTicketStatusUpdateView,
    AdminTicketStatusUpdateView,

    # Admin Ticket Category APIs
    AdminTicketCategoryListView,
    AdminTicketCategoryDetailView,
)


urlpatterns = [
    # Authentication APIs
    path('auth/google/', GoogleLoginView.as_view(), name='google-login'),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Customer APIs
    path(
        'companies/<int:company_id>/complaints/',
        CustomerComplaintCreateView.as_view(),
        name='customer-complaint-create'
    ),
    path(
        'companies/<int:company_id>/customer/tickets/',
        CustomerTicketListView.as_view(),
        name='customer-ticket-list'
    ),

    # Agent APIs
    path(
        'companies/<int:company_id>/agent/complaints/',
        AgentPendingComplaintsView.as_view(),
        name='agent-pending-complaints'
    ),
    path(
        'companies/<int:company_id>/agent/complaints/accept/',
        AgentAcceptComplaintView.as_view(),
        name='agent-accept-complaint'
    ),

    # Admin Agent APIs
    path(
        'companies/<int:company_id>/admin/agents/',
        AdminAgentListView.as_view(),
        name='admin-agent-list'
    ),
    path(
        'companies/<int:company_id>/admin/agents/<int:agent_id>/',
        AdminAgentDetailView.as_view(),
        name='admin-agent-detail'
    ),

    # Admin Customer APIs
    path(
        'companies/<int:company_id>/admin/customers/',
        AdminCustomerListView.as_view(),
        name='admin-customer-list'
    ),
    path(
        'companies/<int:company_id>/admin/customers/<int:customer_id>/',
        AdminCustomerDetailView.as_view(),
        name='admin-customer-detail'
    ),
    path(
        'companies/<int:company_id>/admin/customers/<int:customer_id>/history/',
        AdminCustomerHistoryView.as_view(),
        name='admin-customer-history'
    ),

    # Admin Complaint API
    path(
        'companies/<int:company_id>/admin/complaints/',
        AdminComplaintListView.as_view(),
        name='admin-complaint-list'
    ),

    # Admin Ticket APIs
    path(
        'companies/<int:company_id>/admin/tickets/',
        AdminTicketListView.as_view(),
        name='admin-ticket-list'
    ),
    path(
        'companies/<int:company_id>/admin/tickets/<int:ticket_id>/assign/',
        AdminTicketAssignmentView.as_view(),
        name='admin-ticket-assign'
    ),

    # Ticket Status APIs
    path(
        'companies/<int:company_id>/agent/tickets/<int:ticket_id>/status/',
        AgentTicketStatusUpdateView.as_view(),
        name='agent-ticket-status-update'
    ),
    path(
        'companies/<int:company_id>/admin/tickets/<int:ticket_id>/status/',
        AdminTicketStatusUpdateView.as_view(),
        name='admin-ticket-status-update'
    ),

    # Admin Ticket Category APIs
    path(
        'companies/<int:company_id>/admin/categories/',
        AdminTicketCategoryListView.as_view(),
        name='admin-ticket-category-list'
    ),
    path(
        'companies/<int:company_id>/admin/categories/<int:category_id>/',
        AdminTicketCategoryDetailView.as_view(),
        name='admin-ticket-category-detail'
    ),
]