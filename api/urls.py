
from django.urls import path

from rest_framework_simplejwt.views import TokenRefreshView

from api.advanced_views import (\n    FAQView, FAQCategoryView, SLAPolicyView, NotificationListView,\n    LiveChatView, LiveChatMessageView, LiveChatAcceptView,\n    TicketFeedbackView, CompanyReportsView, AuditLogView, CompanySettingsView,\n)\n\nfrom api.views import (
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
    TicketConversationView,

    # Admin Ticket Category APIs
    AdminTicketCategoryListView,
    AdminTicketCategoryDetailView,
)


urlpatterns = [\n
    # FAQ and Knowledge Base
    path('companies/<int:company_id>/faqs/', FAQView.as_view(), name='company-faqs'),
    path('companies/<int:company_id>/faq-categories/', FAQCategoryView.as_view(), name='faq-categories'),

    # SLA Policies
    path('companies/<int:company_id>/admin/sla-policies/', SLAPolicyView.as_view(), name='sla-policies'),

    # Notifications
    path('companies/<int:company_id>/notifications/', NotificationListView.as_view(), name='notifications'),

    # Live Chat
    path('companies/<int:company_id>/live-chat/', LiveChatView.as_view(), name='live-chat'),
    path('companies/<int:company_id>/live-chat/<int:session_id>/messages/', LiveChatMessageView.as_view(), name='live-chat-messages'),
    path('companies/<int:company_id>/live-chat/<int:session_id>/accept/', LiveChatAcceptView.as_view(), name='live-chat-accept'),

    # Feedback, reports, audit and company settings
    path('companies/<int:company_id>/tickets/<int:ticket_id>/feedback/', TicketFeedbackView.as_view(), name='ticket-feedback'),
    path('companies/<int:company_id>/admin/reports/', CompanyReportsView.as_view(), name='company-reports'),
    path('companies/<int:company_id>/admin/audit-logs/', AuditLogView.as_view(), name='audit-logs'),
    path('companies/<int:company_id>/admin/settings/', CompanySettingsView.as_view(), name='company-settings'),

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

    # Ticket Conversations
    path(
        'companies/<int:company_id>/tickets/<int:ticket_id>/messages/',
        TicketConversationView.as_view(),
        name='ticket-conversation',
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