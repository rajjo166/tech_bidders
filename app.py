import os
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# -----------------------------
# Production configuration
# -----------------------------
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "dev-only-change-this-secret-key"
)

database_url = os.getenv("DATABASE_URL", "sqlite:///booking.db")

# Render/Postgres may provide postgres://; SQLAlchemy expects postgresql://.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please login to continue."
login_manager.login_message_category = "warning"

# Correct scheme/host handling behind Render's reverse proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# -----------------------------
# Database models
# -----------------------------
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)

    bookings = db.relationship(
        "Booking",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Resource(db.Model):
    __tablename__ = "resource"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    resource_type = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    capacity = db.Column(db.Integer, default=1, nullable=False)
    description = db.Column(db.Text, default="")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    bookings = db.relationship(
        "Booking",
        backref="resource",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resource.id"),
        nullable=False,
        index=True
    )
    booking_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="Pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def has_conflict(self):
        existing = Booking.query.filter(
            Booking.resource_id == self.resource_id,
            Booking.booking_date == self.booking_date,
            Booking.status.in_(["Pending", "Approved"]),
            Booking.id != self.id
        ).all()

        return any(
            self.start_time < b.end_time and self.end_time > b.start_time
            for b in existing
        )


# -----------------------------
# Login
# -----------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# -----------------------------
# Automatic database bootstrap
# -----------------------------
def initialize_database():
    """
    Creates all tables and seeds the first admin/resources.
    This runs automatically when the Render service starts.
    """
    with app.app_context():
        db.create_all()

        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")

        admin = User.query.filter_by(email=admin_email).first()
        if not admin:
            admin = User(
                name="Administrator",
                email=admin_email,
                role="admin"
            )
            admin.set_password(admin_password)
            db.session.add(admin)

        if Resource.query.count() == 0:
            db.session.add_all([
                Resource(
                    name="Computer Lab A",
                    resource_type="Laboratory",
                    location="Block A - 2nd Floor",
                    capacity=60,
                    description="60-seat computer laboratory with projector."
                ),
                Resource(
                    name="Seminar Hall",
                    resource_type="Hall",
                    location="Main Building",
                    capacity=200,
                    description="Large hall suitable for seminars and events."
                ),
                Resource(
                    name="Meeting Room 1",
                    resource_type="Meeting Room",
                    location="Admin Block",
                    capacity=12,
                    description="Small meeting room with display and whiteboard."
                ),
            ])

        db.session.commit()


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    resources = (
        Resource.query
        .filter_by(is_active=True)
        .order_by(Resource.name)
        .all()
    )
    return render_template("index.html", resources=resources)


@app.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok", "database": "connected"})
    except Exception as exc:
        app.logger.exception("Health check failed")
        return jsonify({"status": "error", "database": str(exc)}), 503


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("register"))

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Welcome back!", "success")
            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    bookings = (
        Booking.query
        .filter_by(user_id=current_user.id)
        .order_by(
            Booking.booking_date.desc(),
            Booking.start_time.desc()
        )
        .all()
    )
    return render_template("dashboard.html", bookings=bookings)


@app.route("/book/<int:resource_id>", methods=["GET", "POST"])
@login_required
def book(resource_id):
    resource = db.get_or_404(Resource, resource_id)

    if not resource.is_active:
        flash("This resource is currently unavailable.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        try:
            booking_date = datetime.strptime(
                request.form.get("booking_date", ""),
                "%Y-%m-%d"
            ).date()
            start_time = datetime.strptime(
                request.form.get("start_time", ""),
                "%H:%M"
            ).time()
            end_time = datetime.strptime(
                request.form.get("end_time", ""),
                "%H:%M"
            ).time()
        except ValueError:
            flash("Please enter a valid date and time.", "danger")
            return redirect(url_for("book", resource_id=resource.id))

        purpose = request.form.get("purpose", "").strip()

        if end_time <= start_time:
            flash("End time must be after start time.", "danger")
            return redirect(url_for("book", resource_id=resource.id))

        if booking_date < datetime.now().date():
            flash("Booking date cannot be in the past.", "danger")
            return redirect(url_for("book", resource_id=resource.id))

        if not purpose:
            flash("Please enter the purpose of the booking.", "danger")
            return redirect(url_for("book", resource_id=resource.id))

        booking = Booking(
            user_id=current_user.id,
            resource_id=resource.id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            purpose=purpose
        )

        if booking.has_conflict():
            flash(
                "This resource is already booked during the selected time.",
                "danger"
            )
            return redirect(url_for("book", resource_id=resource.id))

        db.session.add(booking)
        db.session.commit()

        flash("Booking request submitted successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("book.html", resource=resource)


@app.route("/cancel/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)

    if booking.user_id != current_user.id and current_user.role != "admin":
        abort(403)

    if booking.status != "Cancelled":
        booking.status = "Cancelled"
        db.session.commit()
        flash("Booking cancelled.", "success")

    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    resources = Resource.query.order_by(Resource.name).all()
    bookings = (
        Booking.query
        .order_by(
            Booking.booking_date.desc(),
            Booking.start_time.desc()
        )
        .all()
    )
    users = User.query.order_by(User.name).all()

    return render_template(
        "admin.html",
        resources=resources,
        bookings=bookings,
        users=users
    )


@app.route("/admin/resource/add", methods=["GET", "POST"])
@admin_required
def add_resource():
    if request.method == "POST":
        try:
            capacity = int(request.form.get("capacity", 1))
        except ValueError:
            capacity = 1

        if capacity < 1:
            capacity = 1

        resource = Resource(
            name=request.form.get("name", "").strip(),
            resource_type=request.form.get("resource_type", "").strip(),
            location=request.form.get("location", "").strip(),
            capacity=capacity,
            description=request.form.get("description", "").strip(),
            is_active=True
        )

        if not resource.name or not resource.resource_type or not resource.location:
            flash("Name, type and location are required.", "danger")
            return redirect(url_for("add_resource"))

        db.session.add(resource)
        db.session.commit()

        flash("Resource added.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("resource_form.html", resource=None)


@app.route("/admin/resource/<int:resource_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)

    if request.method == "POST":
        try:
            capacity = int(request.form.get("capacity", 1))
        except ValueError:
            capacity = 1

        resource.name = request.form.get("name", "").strip()
        resource.resource_type = request.form.get("resource_type", "").strip()
        resource.location = request.form.get("location", "").strip()
        resource.capacity = max(1, capacity)
        resource.description = request.form.get("description", "").strip()
        resource.is_active = "is_active" in request.form

        if not resource.name or not resource.resource_type or not resource.location:
            flash("Name, type and location are required.", "danger")
            return redirect(
                url_for("edit_resource", resource_id=resource.id)
            )

        db.session.commit()
        flash("Resource updated.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("resource_form.html", resource=resource)


@app.route("/admin/resource/<int:resource_id>/delete", methods=["POST"])
@admin_required
def delete_resource(resource_id):
    resource = db.get_or_404(Resource, resource_id)

    if resource.bookings:
        resource.is_active = False
        db.session.commit()
        flash(
            "Resource has bookings, so it was deactivated instead of deleted.",
            "info"
        )
    else:
        db.session.delete(resource)
        db.session.commit()
        flash("Resource deleted.", "success")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/booking/<int:booking_id>/<action>", methods=["POST"])
@admin_required
def booking_action(booking_id, action):
    booking = db.get_or_404(Booking, booking_id)

    if action == "approve":
        if booking.status != "Pending":
            flash("Only pending bookings can be approved.", "warning")
            return redirect(url_for("admin_dashboard"))

        if booking.has_conflict():
            flash(
                "Cannot approve: another booking conflicts with this time.",
                "danger"
            )
            return redirect(url_for("admin_dashboard"))

        booking.status = "Approved"

    elif action == "reject":
        if booking.status != "Pending":
            flash("Only pending bookings can be rejected.", "warning")
            return redirect(url_for("admin_dashboard"))

        booking.status = "Rejected"

    else:
        abort(400)

    db.session.commit()
    flash(f"Booking {action}d.", "success")
    return redirect(url_for("admin_dashboard"))


# Backward-compatible CLI command.
@app.cli.command("init-db")
def init_db():
    initialize_database()
    print("Database initialized.")
    print(
        "Admin login:",
        os.getenv("ADMIN_EMAIL", "admin@example.com"),
        "/",
        os.getenv("ADMIN_PASSWORD", "Admin@123")
    )


# Automatically create/seed the database when Gunicorn starts.
# This fixes the Render 'no such table: resource' problem.
try:
    initialize_database()
except Exception:
    # Let Gunicorn start so Render logs show the actual database error.
    app.logger.exception("Automatic database initialization failed.")


if __name__ == "__main__":
    app.run(debug=True)
