# API reference

All endpoints are prefixed with `/api/`. Except registration and login, endpoints require a JWT access token in the Authorization header:

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

Company-scoped endpoints require an active membership in the URL company. Admin endpoints require the company_admin role.

## Authentication
- `POST auth/register/`: username, email, password, confirm_password, first_name?, last_name?
- `POST auth/login/`: email, password
- `POST auth/google/`: id_token
- `POST auth/token/refresh/`: refresh

## Ticket conversations
- `GET companies/{company_id}/tickets/{ticket_id}/messages/`
- `POST companies/{company_id}/tickets/{ticket_id}/messages/`
- JSON body: `{"message":"Please see the attached details","is_internal":false}`
- For multipart uploads, use `message`, optional `is_internal`, and repeat the `attachments` field. Up to five files, 10 MB each. Customers cannot create or view internal notes.

## FAQ / knowledge base
- `GET companies/{company_id}/faqs/`: active company members; published articles only.
- `GET companies/{company_id}/faq-categories/`
- `POST companies/{company_id}/faq-categories/` (admin): `{"name":"Accounts","description":"Account help"}`
- `POST companies/{company_id}/faqs/` (admin): `{"category":1,"question":"How do I reset my password?","answer":"Use the reset link.","is_published":true}`

## SLA
- `GET companies/{company_id}/admin/sla-policies/`
- `POST companies/{company_id}/admin/sla-policies/`: `{"name":"Standard","priority":"medium","first_response_minutes":240,"resolution_minutes":1440}`
- New tickets automatically receive the active medium-priority policy when one exists. Due times are stored in TicketSLA.

## Notifications
- `GET companies/{company_id}/notifications/`
- `PATCH companies/{company_id}/notifications/`: `{"ids":[1,2]}` or omit ids to mark all current user's notifications read.
- Ticket creation and status changes create customer notifications.

## Live chat
- `POST companies/{company_id}/live-chat/` (customer): `{"subject":"Need help"}`
- `GET companies/{company_id}/live-chat/`
- `PATCH companies/{company_id}/live-chat/{session_id}/accept/` (agent/admin)
- `GET/POST companies/{company_id}/live-chat/{session_id}/messages/`: POST `{"message":"Hello"}`
- This is REST-based messaging, not a real-time WebSocket transport.

## Feedback
- `POST companies/{company_id}/tickets/{ticket_id}/feedback/` (ticket owner, resolved/closed ticket): `{"rating":5,"comment":"Great support"}`
- One feedback record per ticket; rating must be 1-5.

## Reports, audit, settings
- `GET companies/{company_id}/admin/reports/`: ticket counts/status/category, customers, feedback average, live-chat counts.
- `GET companies/{company_id}/admin/audit-logs/?action=ticket.feedback_submitted`
- `GET companies/{company_id}/admin/settings/`
- `PATCH companies/{company_id}/admin/settings/`: JSON object with supported keys: `company_profile`, `business_hours`, `notification_preferences`, `ticket_preferences`.

## Deployment checklist
Use DEBUG=false, a strong DJANGO_SECRET_KEY, restricted ALLOWED_HOSTS, HTTPS, MySQL/PostgreSQL, persistent private media storage, backups, static file serving, log monitoring and malware scanning for uploaded files. Do not expose Django's development server in production.
