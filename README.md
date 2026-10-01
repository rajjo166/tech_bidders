# Resource Booking & Scheduling — Render Ready

A complete Flask full-stack college project with:
- Flask + SQLAlchemy
- PostgreSQL support for Render
- SQLite fallback for local development
- Automatic database table creation on startup
- Automatic seed data
- Admin authentication
- User registration/login
- Resource CRUD
- Booking creation/cancellation
- Booking conflict detection
- Admin approval/rejection
- Health check at `/health`
- Render Blueprint (`render.yaml`) that creates the web service and PostgreSQL database

## Fastest Render deployment

### Option A — Render Blueprint (recommended)

1. Push this project to GitHub.
2. In Render, choose **New → Blueprint**.
3. Select the GitHub repository.
4. Render reads `render.yaml`.
5. It creates:
   - `tech-bidders` web service
   - `tech-bidders-db` PostgreSQL database
   - `DATABASE_URL` automatically connected to the web service
   - a generated `SECRET_KEY`
6. When asked for `ADMIN_PASSWORD`, enter a strong password.
7. Deploy.

Render Blueprints use `fromDatabase` to inject the PostgreSQL connection string into `DATABASE_URL`.

### Option B — Existing Render Web Service

Set:
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --bind 0.0.0.0:$PORT app:app`

Create a Render PostgreSQL database and set its internal connection string as:
- `DATABASE_URL`

Also set:
- `SECRET_KEY` = a long random secret
- `ADMIN_EMAIL` = your admin email
- `ADMIN_PASSWORD` = your admin password

The application automatically runs `db.create_all()` and seeds the admin/sample resources on startup.

## Local development

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
flask --app app run --debug
```

Open:
`http://127.0.0.1:5000`

Local fallback database:
`booking.db`

## Default admin

If no environment variables are supplied:

- Email: `admin@example.com`
- Password: `Admin@123`

For deployment, set `ADMIN_PASSWORD` in Render and change it from the default.

## Important

The application is designed to use PostgreSQL on Render. Do not rely on the local SQLite database for production persistence.
