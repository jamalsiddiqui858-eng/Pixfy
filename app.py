import time
from flask import Flask, render_template, request, send_file, redirect, url_for, session
import os
import img2pdf
from PIL import Image
from PyPDF2 import PdfMerger
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ================= DATABASE =================

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        plan TEXT DEFAULT 'free',
        usage_count INTEGER DEFAULT 0,
        last_used TEXT
    )''')

    conn.commit()
    conn.close()

init_db()


# ================= HOME =================

@app.route("/")
def home():
    user_logged_in = "user_id" in session
    user_name = session.get("user_name")

    return render_template("home.html", user_logged_in=user_logged_in, user_name=user_name)


# ================= SIGNUP =================

@app.route("/signup", methods=["GET","POST"])
def signup():

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                    (name,email,hashed_password))
            conn.commit()
        except:
            return "Email already exists!"

        conn.close()
        return redirect(url_for("login"))

    return render_template("signup.html")


# ================= LOGIN =================

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            return redirect(url_for("dashboard"))
        else:
            return "Invalid login!"

    return render_template("login.html")


# ================= LOGOUT =================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ================= DASHBOARD =================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT plan FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    user_plan = user[0]

    return render_template(
        "dashboard.html",
        user_name=session.get("user_name"),
        user_plan=user_plan
    )


# ================= UPGRADE =================

@app.route("/upgrade/<plan>")
def upgrade(plan):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE users SET plan=? WHERE id=?", (plan, session["user_id"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


# ================= CHECK LIMIT =================

def check_limit(user_id):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT plan, usage_count, last_used FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    plan, usage, last_used = user

    today = datetime.now().date()

    if last_used:
        last_used = datetime.strptime(last_used, "%Y-%m-%d").date()

    if last_used != today:
        usage = 0

    # premium unlimited
    if plan == "premium":
        return True

    if plan == "free" and usage >= 1:
        return False

    if plan == "pro" and usage >= 50:
        return False

    usage += 1

    c.execute("UPDATE users SET usage_count=?, last_used=? WHERE id=?",
            (usage, str(today), user_id))

    conn.commit()
    conn.close()

    return True


# ================= IMAGE TO PDF =================

@app.route("/image-to-pdf", methods=["GET","POST"])
def image_to_pdf():

    if "user_id" not in session:
        return redirect("/login")

    if not check_limit(session["user_id"]):
        return "Limit reached! Upgrade plan."

    if request.method == "POST":

        files = request.files.getlist("images")
        paths = []

        for file in files:
            path = os.path.join(UPLOAD_FOLDER, str(time.time()) + file.filename)
            file.save(path)
            paths.append(path)

        output = os.path.join(UPLOAD_FOLDER, str(int(time.time())) + ".pdf")

        with open(output, "wb") as f:
            f.write(img2pdf.convert(paths))

        return send_file(output, as_attachment=True)

    return render_template("image_to_pdf.html")


# ================= SPLIT IMAGE =================

@app.route("/split-image", methods=["GET","POST"])
def split_image():

    if "user_id" not in session:
        return redirect("/login")

    if not check_limit(session["user_id"]):
        return "Limit reached!"

    if request.method == "POST":

        file = request.files["image"]
        path = os.path.join(UPLOAD_FOLDER, str(time.time()) + file.filename)
        file.save(path)

        img = Image.open(path)
        width, height = img.size

        left = img.crop((0, 0, width//2, height))
        right = img.crop((width//2, 0, width, height))

        left_path = os.path.join(UPLOAD_FOLDER, str(time.time()) + "_left.png")
        right_path = os.path.join(UPLOAD_FOLDER, str(time.time()) + "_right.png")

        left.save(left_path)
        right.save(right_path)

        return send_file(left_path, as_attachment=True)

    return render_template("split_image.html")


# ================= COMPRESS IMAGE =================

@app.route("/compress-image", methods=["GET","POST"])
def compress_image():

    if "user_id" not in session:
        return redirect("/login")

    if not check_limit(session["user_id"]):
        return "Limit reached!"

    if request.method == "POST":

        file = request.files["image"]
        path = os.path.join(UPLOAD_FOLDER, str(time.time()) + file.filename)
        file.save(path)

        img = Image.open(path)

        output = os.path.join(UPLOAD_FOLDER, str(int(time.time())) + ".jpg")
        img.save(output, "JPEG", quality=30)

        return send_file(output, as_attachment=True)

    return render_template("compress_image.html")


# ================= MERGE PDF =================

@app.route("/merge-pdf", methods=["GET","POST"])
def merge_pdf():

    if "user_id" not in session:
        return redirect("/login")

    if not check_limit(session["user_id"]):
        return "Limit reached!"

    if request.method == "POST":

        files = request.files.getlist("pdfs")
        merger = PdfMerger()

        for file in files:
            path = os.path.join(UPLOAD_FOLDER, str(time.time()) + file.filename)
            file.save(path)
            merger.append(path)

        output = os.path.join(UPLOAD_FOLDER, str(int(time.time())) + ".pdf")
        merger.write(output)
        merger.close()

        return send_file(output, as_attachment=True)

    return render_template("merge_pdf.html")


if __name__ == "__main__":
    app.run(debug=True)