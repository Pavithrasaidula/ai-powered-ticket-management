# AI-Powered Ticket Management System

Django REST Framework backend for multi-company ticket management.

## Backend layout

All Django application code, project configuration, migrations, and Python dependencies are under `backend/`. Postman collections remain at the repository root in `postman/`.

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```powershell
   cd backend
   pip install -r requirements.txt
   ```

3. From the repository root, copy `.env.example` to `.env` and set a strong `DJANGO_SECRET_KEY`.
4. Run migrations and start the development server:

   ```powershell
   python manage.py migrate
   python manage.py check
   python manage.py runserver
   ```

The API is served under `/api/`; Django admin is under `/admin/`.

## Database

SQLite is the default for local development. Set `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` to use MySQL. Never commit real credentials.

## API overview

- Authentication: `/api/auth/register/`, `/api/auth/login/`, `/api/auth/google/`
- Customer complaints and tickets: `/api/companies/{company_id}/complaints/`, `/api/companies/{company_id}/customer/tickets/`
- Agent complaints and ticket status: `/api/companies/{company_id}/agent/complaints/`, `/api/companies/{company_id}/agent/tickets/{ticket_id}/status/`
- Admin agents, customers, categories, assignment, status, SLA policies, reports, audit logs and settings: `/api/companies/{company_id}/admin/...`
- Ticket conversation: `/api/companies/{company_id}/tickets/{ticket_id}/messages/`
- FAQ: `/api/companies/{company_id}/faqs/`
- Notifications: `/api/companies/{company_id}/notifications/`
- Live chat: `/api/companies/{company_id}/live-chat/`
- Customer feedback: `/api/companies/{company_id}/tickets/{ticket_id}/feedback/`

See `docs/API.md` for request examples and permissions.

## Docker deployment

Set `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS` in the root `.env` file. Then run:

```powershell
docker compose up --build -d
```

The backend container applies migrations and collects static files before starting Gunicorn. Use HTTPS through a reverse proxy and configure the secure cookie/redirect settings for production.

## Validation

GitHub Actions runs Django system checks, checks that model changes have migrations, and executes the test suite on pushes and pull requests.

## Notes

- This repository contains backend APIs only. Frontend and AI-provider integration are intentionally excluded.
- Live chat currently uses REST polling endpoints; it is not a WebSocket implementation.
- Configure a production secret key, hosts, HTTPS, database, static/media storage and file scanning before deployment.
