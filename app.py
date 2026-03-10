import os
import random
import redis
import smtplib
from functools import wraps
from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from email.message import EmailMessage

load_dotenv()

# ---------------- EMAIL CONFIG ----------------
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM")

# ---------------- REDIS CONFIG ----------------
REDIS_SERVER_NUMBER = os.getenv("REDIS_SERVER_NUMBER")
REDIS_PORT_NUMBER = int(os.getenv("REDIS_PORT_NUMBER", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

redis_client = redis.Redis(
    host=REDIS_SERVER_NUMBER,
    port=REDIS_PORT_NUMBER,
    password=REDIS_PASSWORD,
    decode_responses=True
)

# ---------------- APP ----------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# ---------------- ADMIN CREDENTIALS ----------------
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# ---------------- MODELS ----------------
class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    url = db.Column(db.String(300), nullable=False)

class FileUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    filename = db.Column(db.String(300), nullable=False)

class Collaborator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    resume_url = db.Column(db.String(300), nullable=False)
    contribution = db.Column(db.String(300), nullable=False)

# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access only", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("resources"))

# ---------------- ADMIN AUTH ----------------
@app.route("/admin-entry")
def admin_entry():
    if session.get("is_admin"):
        session.pop("is_admin")
        flash("Logged out", "info")
        return redirect(url_for("resources"))
    return redirect(url_for("admin_login"))

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Login successful", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")

    return render_template("admin_login.html")

@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out", "info")
    return redirect(url_for("resources"))

# ---------------- PUBLIC RESOURCES ----------------
@app.route("/resources")
def resources():
    links = Link.query.all()
    files = FileUpload.query.all()
    return render_template("resources.html", links=links, files=files)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@admin_required
def dashboard():
    links = Link.query.all()
    files = FileUpload.query.all()
    return render_template("dashboard.html", links=links, files=files)

# ---------------- LINKS ----------------
@app.route("/add-link", methods=["GET","POST"])
@admin_required
def add_link():
    if request.method == "POST":
        db.session.add(Link(
            title=request.form["title"],
            url=request.form["url"]
        ))
        db.session.commit()
        flash("Link added", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_link.html")

@app.route("/edit-link/<int:id>", methods=["GET","POST"])
@admin_required
def edit_link(id):
    link = Link.query.get_or_404(id)

    if request.method == "POST":
        link.title = request.form["title"]
        link.url = request.form["url"]
        db.session.commit()
        flash("Link updated", "success")
        return redirect(url_for("dashboard"))

    return render_template("edit_link.html", link=link)

@app.route("/delete-link/<int:id>", methods=["POST"])
@admin_required
def delete_link(id):
    link = Link.query.get_or_404(id)
    db.session.delete(link)
    db.session.commit()
    flash("Link deleted", "success")
    return redirect(url_for("dashboard"))

# ---------------- FILES ----------------
@app.route("/add-file", methods=["GET","POST"])
@admin_required
def add_file():
    if request.method == "POST":

        if "file" not in request.files:
            flash("No file selected", "danger")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No file selected", "danger")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file type", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db.session.add(FileUpload(
            title=request.form["title"],
            filename=filename
        ))
        db.session.commit()

        flash("File uploaded", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_file.html")

@app.route("/download/<int:id>")
def download(id):
    f = FileUpload.query.get_or_404(id)
    return send_from_directory(app.config["UPLOAD_FOLDER"], f.filename, as_attachment=True)

@app.route("/preview/<int:id>")
def preview_file(id):
    file = FileUpload.query.get_or_404(id)
    return send_from_directory(app.config["UPLOAD_FOLDER"], file.filename)

# ---------------- EMAIL ----------------
def send_email(to, otp):
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = "Eknal Technologies – Email Verification Code"

    msg.set_content(f"Your OTP is: {otp}")

    server = smtplib.SMTP("smtp.zoho.in", 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.send_message(msg)
    server.quit()

# ---------------- OTP ----------------
def generate_otp():
    return str(random.randint(100000, 999999))

def save_otp(email, otp):
    redis_client.setex(f"otp:{email}", 300, otp)

def get_otp(email):
    return redis_client.get(f"otp:{email}")

def delete_otp(email):
    redis_client.delete(f"otp:{email}")

# ---------------- RUN ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
