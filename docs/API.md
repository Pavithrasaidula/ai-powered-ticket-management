# API reference

All endpoints are prefixed with `/api/`. Except registration and login, endpoints require a JWT access token in the Authorization header:

```http
Authorization: Bearer <access-token>
Content-Type: application/json
```

Company-scoped endpoints require an active membership in the URL company. Admin endpoints require the company_admin role.

## Authentication
- `POST auth/company/register/`: company_name, company_slug? plus username, email, password, confirm_password, first_name?, last_name? Creates a company and its first company_admin user. Log in after registration.\n- `POST auth/register/`: company_id, username, email, password, confirm_password, first_name?, last_name? Registers a customer in the selected company. If company_id is omitted, the legacy demo-company is used when present.
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
- `PATCH companies/{company_id}/live-chat/{session_id}/end/`: end an active session (customer owner, assigned agent or company admin)
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


## Complete Postman endpoint map

Use these full local URLs in Postman. Replace the numeric IDs with IDs returned by earlier requests.

### Authentication
| Method | URL | Purpose |
|---|---|---|
| POST | `http://127.0.0.1:8000/api/auth/company/register/` | Register a company and its first admin |
| POST | `http://127.0.0.1:8000/api/auth/register/` | Register a customer using `company_id` |
| POST | `http://127.0.0.1:8000/api/auth/login/` | Login for admin, agent or customer |
| POST | `http://127.0.0.1:8000/api/auth/google/` | Google login |
| POST | `http://127.0.0.1:8000/api/auth/token/refresh/` | Refresh an access token |

### Customer
| Method | URL | Purpose |
|---|---|---|
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/complaints/` | Create a complaint |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/customer/tickets/` | View own tickets and status history |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/tickets/{ticket_id}/messages/` | View ticket conversation |
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/tickets/{ticket_id}/messages/` | Reply to ticket |
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/tickets/{ticket_id}/feedback/` | Rate a resolved/closed ticket |
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/` | Start live chat |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/{session_id}/end/` | End own live chat |

### Agent
| Method | URL | Purpose |
|---|---|---|
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/agent/complaints/` | View pending complaints |
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/agent/complaints/accept/` | Accept complaint and create ticket |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/agent/tickets/{ticket_id}/status/` | Update assigned ticket status |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/` | View available/assigned chats |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/{session_id}/accept/` | Accept a waiting chat |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/{session_id}/messages/` | View chat messages |
| POST | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/{session_id}/messages/` | Send chat message |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/live-chat/{session_id}/end/` | End assigned chat |

### Admin
| Method | URL | Purpose |
|---|---|---|
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/admin/agents/` | List or create agents |
| GET, PUT, PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/agents/{agent_id}/` | View, update or activate/deactivate agent |
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/admin/customers/` | List or create customer records |
| GET, PUT, PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/customers/{customer_id}/` | View or update customer |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/admin/customers/{customer_id}/history/` | View customer complaint/ticket history |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/admin/complaints/` | View company complaints |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/admin/tickets/` | View company tickets |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/tickets/{ticket_id}/assign/` | Assign ticket to an agent |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/tickets/{ticket_id}/status/` | Update ticket status |
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/admin/categories/` | List or create ticket categories |
| GET, PUT, PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/categories/{category_id}/` | View or update ticket category |
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/faq-categories/` | List or create FAQ categories |
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/faqs/` | List published FAQs or create FAQ |
| GET, POST | `http://127.0.0.1:8000/api/companies/{company_id}/admin/sla-policies/` | List or create SLA policies |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/admin/reports/` | View company reports |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/admin/audit-logs/` | View audit logs |
| GET, PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/admin/settings/` | View or update company settings |

### Shared company-member APIs
| Method | URL | Purpose |
|---|---|---|
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/notifications/` | View own notifications |
| PATCH | `http://127.0.0.1:8000/api/companies/{company_id}/notifications/` | Mark own notifications as read |
| GET | `http://127.0.0.1:8000/api/companies/{company_id}/faqs/` | View published company FAQs |

For protected requests, select **Bearer Token** in Postman and paste the access token returned by the matching role's login request. Use separate login requests/tokens for Admin, Agent and Customer.
