from app import app, db, User, Resource, Booking

with app.app_context():
    db.create_all()
    print("Database URI configured:", app.config["SQLALCHEMY_DATABASE_URI"].split("://")[0])
    print("Users:", User.query.count())
    print("Resources:", Resource.query.count())
    print("Bookings:", Booking.query.count())
    print("Deployment database check: OK")
