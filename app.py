from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "site.db")

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
THUMB_DIR = os.path.join(BASE_DIR, "static", "thumbs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

ALLOWED_VIDEO = {"mp4", "webm", "mov", "m4v"}
ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp"}


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()

    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        filename TEXT NOT NULL,
        thumbnail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    con.commit()
    con.close()


def allowed(filename, extensions):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in extensions
    )


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    con = db()

    user = con.execute(
        "SELECT id, username FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    con.close()

    return user


@app.context_processor
def inject_user():
    return {
        "current_user": current_user()
    }


# =========================
# الصفحة الرئيسية
# =========================

@app.route("/")
def home():

    con = db()

    videos = con.execute("""
        SELECT videos.*, users.username
        FROM videos
        JOIN users ON users.id = videos.user_id
        ORDER BY videos.id DESC
    """).fetchall()

    con.close()

    return render_template(
        "index.html",
        videos=videos
    )


# =========================
# البحث
# =========================

@app.route("/search")
def search():

    q = request.args.get("q", "").strip()

    con = db()

    videos = con.execute("""
        SELECT videos.*, users.username
        FROM videos
        JOIN users ON users.id = videos.user_id
        WHERE videos.title LIKE ?
           OR videos.description LIKE ?
        ORDER BY videos.id DESC
    """, (
        f"%{q}%",
        f"%{q}%"
    )).fetchall()

    con.close()

    return render_template(
        "index.html",
        videos=videos,
        query=q
    )


# =========================
# إنشاء حساب
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("دخل اسم المستخدم وكلمة المرور.")
            return redirect(url_for("register"))

        con = db()

        try:

            con.execute(
                """
                INSERT INTO users(username, password)
                VALUES (?, ?)
                """,
                (
                    username,
                    generate_password_hash(password)
                )
            )

            con.commit()

        except sqlite3.IntegrityError:

            con.close()

            flash("اسم المستخدم موجود من قبل.")

            return redirect(url_for("register"))

        con.close()

        flash("تم إنشاء الحساب.")

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================
# تسجيل الدخول
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        con = db()

        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        con.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            return redirect(url_for("home"))

        flash("اسم المستخدم أو كلمة المرور غير صحيحة.")

    return render_template("login.html")


# =========================
# تسجيل الخروج
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# =========================
# صفحة المستخدم
# =========================

@app.route("/user/<int:user_id>")
def profile(user_id):

    con = db()

    user = con.execute(
        """
        SELECT id, username
        FROM users
        WHERE id=?
        """,
        (user_id,)
    ).fetchone()

    if not user:

        con.close()

        abort(404)

    videos = con.execute(
        """
        SELECT *
        FROM videos
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    con.close()

    return render_template(
        "profile.html",
        user=user,
        videos=videos
    )


# =========================
# رفع فيديو
# =========================

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if not current_user():

        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        video = request.files.get("video")

        thumbnail = request.files.get("thumbnail")

        if not title or not video or not video.filename:

            flash("العنوان والفيديو مطلوبان.")

            return redirect(url_for("upload"))

        if not allowed(
            video.filename,
            ALLOWED_VIDEO
        ):

            flash(
                "صيغة الفيديو غير مدعومة."
            )

            return redirect(url_for("upload"))

        video_name = (
            uuid.uuid4().hex
            + "_"
            + secure_filename(video.filename)
        )

        video.save(
            os.path.join(
                UPLOAD_DIR,
                video_name
            )
        )

        thumbnail_name = None

        if thumbnail and thumbnail.filename:

            if not allowed(
                thumbnail.filename,
                ALLOWED_IMAGE
            ):

                flash("صيغة الصورة غير مدعومة.")

                return redirect(url_for("upload"))

            thumbnail_name = (
                uuid.uuid4().hex
                + "_"
                + secure_filename(thumbnail.filename)
            )

            thumbnail.save(
                os.path.join(
                    THUMB_DIR,
                    thumbnail_name
                )
            )

        con = db()

        con.execute(
            """
            INSERT INTO videos
            (
                user_id,
                title,
                description,
                filename,
                thumbnail
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                description,
                video_name,
                thumbnail_name
            )
        )

        con.commit()

        con.close()

        return redirect(url_for("home"))

    return render_template("upload.html")


# =========================
# مشاهدة الفيديو
# =========================

@app.route("/video/<int:video_id>")
def watch(video_id):

    con = db()

    video = con.execute(
        """
        SELECT videos.*, users.username
        FROM videos
        JOIN users
        ON users.id = videos.user_id
        WHERE videos.id=?
        """,
        (video_id,)
    ).fetchone()

    con.close()

    if not video:

        abort(404)

    return render_template(
        "watch.html",
        video=video
    )


# =========================
# حذف الفيديو
# =========================

@app.route(
    "/video/<int:video_id>/delete",
    methods=["POST"]
)
def delete_video(video_id):

    user = current_user()

    if not user:

        return redirect(url_for("login"))

    con = db()

    video = con.execute(
        "SELECT * FROM videos WHERE id=?",
        (video_id,)    ).fetchone()

    if not video:

        con.close()

        abort(404)

    if video["user_id"] != user["id"]:

        con.close()

        abort(403)

    con.execute(
        "DELETE FROM videos WHERE id=?",
        (video_id,)
    )

    con.commit()

    con.close()

    video_path = os.path.join(
        UPLOAD_DIR,
        video["filename"]
    )

    if os.path.exists(video_path):

        os.remove(video_path)

    if video["thumbnail"]:

        thumb_path = os.path.join(
            THUMB_DIR,
            video["thumbnail"]
        )

        if os.path.exists(thumb_path):

            os.remove(thumb_path)

    return redirect(
        url_for(
            "profile",
            user_id=user["id"]
        )
    )
init_db()

if __name__ == "__main__":

    0
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False
    )

