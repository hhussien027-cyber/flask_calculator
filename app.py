from datetime import datetime, timezone
import os
from uuid import uuid4
from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.utils import secure_filename
import ast
import math
import random
from db_config import db, configure_database
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
app.config["DEBUG"] = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes", "on")
configure_database(app)
app.logger.info("Active database URI: %s", app.config["SQLALCHEMY_DATABASE_URI"])
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_PROFILE_IMAGE_SIZE = 2 * 1024 * 1024

db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = "login"
db_initialized = False

PROGRAMMER_BASES = {
    "HEX": 16,
    "DEC": 10,
    "BIN": 2,
    "OCT": 8
}
PROGRAMMER_WORD_SIZES = {8, 16, 32}


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(150), nullable=False, default="")
    profile_image = db.Column(db.String(255), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    history_entries = db.relationship("History", backref="user", lazy=True, cascade="all, delete-orphan")


class History(db.Model):
    __tablename__ = "history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    mode = db.Column(db.String(32), nullable=False, index=True)
    equation = db.Column(db.Text, nullable=False)
    result = db.Column(db.Text, nullable=False)
    context_base = db.Column(db.String(8), nullable=True)
    context_word_size = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized_handler():
    api_paths = ("/calculate", "/calculate_programmer", "/get_history", "/clear_history")
    if request.path.startswith(api_paths):
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for("login"))


@app.before_request
def ensure_database_initialized():
    global db_initialized
    if db_initialized:
        return
    with app.app_context():
        db.create_all()
    db_initialized = True


def save_history_entry(user_id, mode, equation, result, context_base=None, context_word_size=None):
    entry = History(
        user_id=user_id,
        mode=mode,
        equation=equation,
        result=str(result),
        context_base=context_base,
        context_word_size=context_word_size
    )
    db.session.add(entry)
    commit_session("save_history_entry")


def commit_session(operation_name):
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        app.logger.exception("Database commit failed during %s: %s", operation_name, error)
        raise


def get_user_display_name(user):
    normalized = (user.display_name or "").strip()
    return normalized if normalized else user.username


def is_allowed_profile_image(filename):
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS


def is_profile_image_size_valid(file_storage):
    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return file_size <= MAX_PROFILE_IMAGE_SIZE


def remove_profile_image_file(filename):
    if not filename:
        return
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        os.remove(file_path)


def serialize_history_entry(entry):
    return {
        "id": entry.id,
        "equation": entry.equation,
        "result": entry.result,
        "mode": entry.mode,
        "base": entry.context_base,
        "word_size": entry.context_word_size,
        "timestamp": entry.timestamp.isoformat()
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error_message = ""
    if request.method == "POST":
        username = str(request.form.get("username", "")).strip()
        password = str(request.form.get("password", "")).strip()
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for("index"))
        error_message = "Invalid username or password."

    return render_template("login.html", error_message=error_message)


@app.route("/googleb0243657fa846af6.html")
def google_site_verification_file():
    return send_from_directory(app.root_path, "googleb0243657fa846af6.html")


@app.route("/sitemap.xml")
def sitemap_file():
    return send_from_directory(app.root_path, "sitemap.xml", mimetype="application/xml")


@app.route("/robots.txt")
def robots_file():
    return send_from_directory(app.root_path, "robots.txt", mimetype="text/plain")


@app.route("/health/db")
def health_db():
    try:
        ping_value = db.session.execute(text("SELECT 1")).scalar()
        return jsonify({
            "ok": True,
            "database": "connected",
            "ping": int(ping_value) if ping_value is not None else None
        }), 200
    except SQLAlchemyError as error:
        app.logger.exception("Database health check failed: %s", error)
        return jsonify({
            "ok": False,
            "database": "error"
        }), 500


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error_message = ""
    success_message = ""
    if request.method == "POST":
        form_username = str(request.form.get("username", "")).strip()
        password = str(request.form.get("password", "")).strip()
        confirm_password = str(request.form.get("confirm_password", "")).strip()

        if len(form_username) < 3:
            error_message = "Username must be at least 3 characters."
        elif len(password) < 3:
            error_message = "Password must be at least 3 characters."
        elif password != confirm_password:
            error_message = "Passwords do not match."
        else:
            existing_user = User.query.filter_by(username=form_username).first()
            if existing_user:
                flash("Username already exists. Please choose another one.", "error")
                return redirect(url_for("signup"))
            new_user = User(
                username=form_username,
                display_name=form_username,
                password=password
            )
            try:
                db.session.add(new_user)
                commit_session("signup")
                session["signup_success_ready"] = True
                return redirect(url_for("signup_success"))
            except IntegrityError:
                db.session.rollback()
                flash("Username already exists. Please choose another one.", "error")
                return redirect(url_for("signup"))
            except SQLAlchemyError:
                flash("Database error while creating account. Please try again.", "error")
                return redirect(url_for("signup"))

    return render_template("signup.html", error_message=error_message, success_message=success_message)


@app.route("/signup-success")
def signup_success():
    if not session.pop("signup_success_ready", False):
        return redirect(url_for("signup"))
    return render_template("signup_success.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    return redirect(url_for("change_password"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        display_name = str(request.form.get("display_name", "")).strip()
        profile_image = request.files.get("profile_image")

        if len(display_name) < 2:
            flash("Display name must be at least 2 characters.", "error")
            return redirect(url_for("profile"))

        current_user.display_name = display_name

        if profile_image and profile_image.filename:
            if not is_allowed_profile_image(profile_image.filename):
                flash("Only PNG, JPG, and JPEG images are allowed.", "error")
                return redirect(url_for("profile"))
            if not is_profile_image_size_valid(profile_image):
                flash("Profile image must be 2MB or smaller.", "error")
                return redirect(url_for("profile"))
            extension = profile_image.filename.rsplit(".", 1)[1].lower()
            unique_filename = secure_filename(f"user_{current_user.id}_{uuid4().hex}.{extension}")
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            previous_image = current_user.profile_image
            profile_image.save(os.path.join(UPLOAD_FOLDER, unique_filename))
            current_user.profile_image = unique_filename
            if previous_image and previous_image != unique_filename:
                remove_profile_image_file(previous_image)

        try:
            commit_session("profile_update")
        except SQLAlchemyError:
            flash("Database error while saving profile. Please try again.", "error")
            return redirect(url_for("profile"))
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template(
        "profile.html",
        display_name=get_user_display_name(current_user),
        profile_image=current_user.profile_image
    )


@app.route("/profile/verify-password", methods=["GET", "POST"])
@login_required
def verify_username_password():
    if request.method == "POST":
        current_password = str(request.form.get("current_password", "")).strip()
        if current_user.password != current_password:
            flash("Current password is incorrect.", "error")
            return redirect(url_for("verify_username_password"))
        session["username_change_verified"] = True
        flash("Password verified. You can update your username now.", "success")
        return redirect(url_for("change_username"))
    return render_template("verify_username.html")


@app.route("/profile/change-username", methods=["GET", "POST"])
@login_required
def change_username():
    if not session.get("username_change_verified"):
        flash("Please verify your password before changing username.", "error")
        return redirect(url_for("verify_username_password"))

    if request.method == "POST":
        new_username = str(request.form.get("new_username", "")).strip()
        confirm_username = str(request.form.get("confirm_username", "")).strip()

        if len(new_username) < 3:
            flash("Username must be at least 3 characters.", "error")
        elif new_username != confirm_username:
            flash("Username and confirmation do not match.", "error")
        elif User.query.filter(User.username == new_username, User.id != current_user.id).first():
            flash("Username already exists.", "error")
        else:
            old_username = current_user.username
            current_user.username = new_username
            if (current_user.display_name or "").strip() in ("", old_username):
                current_user.display_name = new_username
            try:
                db.session.commit()
                session.pop("username_change_verified", None)
                flash("Username updated successfully.", "success")
                return redirect(url_for("profile"))
            except IntegrityError:
                db.session.rollback()
                flash("Username already exists. Please choose another one.", "error")
                return redirect(url_for("change_username"))

    return render_template("change_username.html")


@app.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = str(request.form.get("current_password", "")).strip()
        new_password = str(request.form.get("new_password", "")).strip()
        confirm_new_password = str(request.form.get("confirm_new_password", "")).strip()

        if current_user.password != current_password:
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 3:
            flash("New password must be at least 3 characters.", "error")
        elif new_password != confirm_new_password:
            flash("New password and confirmation do not match.", "error")
        elif current_user.password == new_password:
            flash("New password must be different from the current password.", "error")
        else:
            current_user.password = new_password
            try:
                commit_session("change_password")
            except SQLAlchemyError:
                flash("Database error while updating password. Please try again.", "error")
                return redirect(url_for("change_password"))
            flash("Password updated successfully.", "success")
            return redirect(url_for("change_password"))

    return render_template("change_password.html")


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/calculate", methods=["POST"])
@login_required
def calculate():
    data = request.get_json(silent=True) or {}
    equation = str(data.get("equation", "")).strip()
    angle_mode = str(data.get("angle_mode", "DEG")).upper().strip()

    if not equation:
        return jsonify({"error": "Syntax Error"}), 400

    try:
        result = evaluate_equation(equation, angle_mode)
        normalized_result = normalize_result(result)
        save_history_entry(current_user.id, "standard", equation, normalized_result)
        return jsonify({"result": normalized_result})
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return jsonify({"error": "Syntax Error"}), 400


@app.route("/calculate_programmer", methods=["POST"])
@login_required
def calculate_programmer():
    data = request.get_json(silent=True) or {}
    equation = str(data.get("equation", "")).strip()
    number_base = str(data.get("number_base", "DEC")).upper().strip()

    if not equation:
        return jsonify({"error": "Syntax Error"}), 400

    try:
        word_size = int(data.get("word_size", 32))
        skip_history = bool(data.get("skip_history"))
        result = evaluate_programmer_equation(equation, number_base, word_size)
        formatted = format_programmer_result(result, number_base)
        if not skip_history:
            save_history_entry(
                current_user.id,
                "programmer",
                equation,
                formatted,
                context_base=number_base,
                context_word_size=word_size
            )
        return jsonify({
            "result": formatted,
            "base": number_base,
            "word_size": word_size
        })
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return jsonify({"error": "Syntax Error"}), 400


@app.route("/get_history", methods=["GET"])
@login_required
def get_history():
    mode = str(request.args.get("mode", "standard")).strip().lower()
    if mode not in ("standard", "programmer"):
        return jsonify({"error": "Invalid mode"}), 400

    limit = int(request.args.get("limit", 50))
    safe_limit = max(1, min(limit, 100))
    rows = (
        History.query
        .filter_by(user_id=current_user.id, mode=mode)
        .order_by(History.timestamp.desc())
        .limit(safe_limit)
        .all()
    )
    return jsonify({"history": [serialize_history_entry(row) for row in rows]})


@app.route("/clear_history", methods=["POST"])
@login_required
def clear_history():
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode", "standard")).strip().lower()
    if mode not in ("standard", "programmer"):
        return jsonify({"error": "Invalid mode"}), 400

    try:
        History.query.filter_by(user_id=current_user.id, mode=mode).delete()
        commit_session("clear_history")
    except SQLAlchemyError:
        return jsonify({"error": "Database write error"}), 500
    return jsonify({"ok": True})


@app.route("/save_history", methods=["POST"])
@login_required
def save_history():
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode", "standard")).strip().lower()
    equation = str(data.get("equation", "")).strip()
    result = str(data.get("result", "")).strip()
    base = str(data.get("base", "")).upper().strip() or None
    word_size_raw = data.get("word_size")

    if mode not in ("standard", "programmer"):
        return jsonify({"error": "Invalid mode"}), 400
    if not equation or not result:
        return jsonify({"error": "Invalid history payload"}), 400

    context_word_size = None
    if word_size_raw is not None:
        context_word_size = int(word_size_raw)
        if context_word_size not in PROGRAMMER_WORD_SIZES:
            return jsonify({"error": "Invalid word size"}), 400

    save_history_entry(
        current_user.id,
        mode,
        equation,
        result,
        context_base=base,
        context_word_size=context_word_size
    )
    return jsonify({"ok": True})


def trig_sin(value, angle_mode):
    if angle_mode == "RAD":
        return math.sin(value)
    return math.sin(math.radians(value))


def trig_cos(value, angle_mode):
    if angle_mode == "RAD":
        return math.cos(value)
    return math.cos(math.radians(value))


def trig_tan(value, angle_mode):
    if angle_mode == "RAD":
        return math.tan(value)
    return math.tan(math.radians(value))


def trig_asin(value, angle_mode):
    result = math.asin(value)
    if angle_mode == "RAD":
        return result
    return math.degrees(result)


def trig_acos(value, angle_mode):
    result = math.acos(value)
    if angle_mode == "RAD":
        return result
    return math.degrees(result)


def trig_atan(value, angle_mode):
    result = math.atan(value)
    if angle_mode == "RAD":
        return result
    return math.degrees(result)


def trig_csc(value, angle_mode):
    return 1 / trig_sin(value, angle_mode)


def trig_sec(value, angle_mode):
    return 1 / trig_cos(value, angle_mode)


def trig_cot(value, angle_mode):
    return 1 / trig_tan(value, angle_mode)


def trig_acsc(value, angle_mode):
    return trig_asin(1 / value, angle_mode)


def trig_asec(value, angle_mode):
    return trig_acos(1 / value, angle_mode)


def trig_acot(value, angle_mode):
    return trig_atan(1 / value, angle_mode)


def csch(value):
    return 1 / math.sinh(value)


def sech(value):
    return 1 / math.cosh(value)


def coth(value):
    return 1 / math.tanh(value)


def acsch(value):
    return math.asinh(1 / value)


def asech(value):
    return math.acosh(1 / value)


def acoth(value):
    return math.atanh(1 / value)


def safe_factorial(value):
    if not float(value).is_integer() or value < 0:
        raise ValueError("Invalid factorial input")
    return math.factorial(int(value))


def safe_perm(n, r):
    nf = float(n)
    rf = float(r)
    if not nf.is_integer() or not rf.is_integer():
        raise ValueError("Invalid permutation input")
    ni = int(nf)
    ri = int(rf)
    if ri < 0 or ni < 0 or ri > ni:
        raise ValueError("Invalid permutation input")
    return math.factorial(ni) // math.factorial(ni - ri)


def safe_comb(n, r):
    nf = float(n)
    rf = float(r)
    if not nf.is_integer() or not rf.is_integer():
        raise ValueError("Invalid combination input")
    ni = int(nf)
    ri = int(rf)
    if ri < 0 or ni < 0 or ri > ni:
        raise ValueError("Invalid combination input")
    return math.comb(ni, ri)


def random_number():
    return random.random()


def nth_root(base, degree):
    if degree == 0:
        raise ZeroDivisionError("Root degree cannot be zero")
    return base ** (1 / degree)


def find_matching_paren(text, open_index):
    depth = 0
    for index in range(open_index, len(text)):
        current = text[index]
        if current == "(":
            depth += 1
        elif current == ")":
            depth -= 1
            if depth == 0:
                return index
    raise SyntaxError("Unmatched parentheses")


def split_top_level_args(text):
    depth = 0
    for index, current in enumerate(text):
        if current == "(":
            depth += 1
        elif current == ")":
            depth -= 1
        elif current == "," and depth == 0:
            first = text[:index].strip()
            second = text[index + 1:].strip()
            if not first or not second:
                raise SyntaxError("Invalid root arguments")
            return first, second
    raise SyntaxError("Root requires two arguments")


def normalize_nth_root_notation(equation):
    normalized = equation
    for token in ("ⁿ√(", "n√("):
        while token in normalized:
            token_index = normalized.find(token)
            open_index = token_index + len(token) - 1
            close_index = find_matching_paren(normalized, open_index)
            inner_expression = normalized[open_index + 1:close_index]
            degree_expression, base_expression = split_top_level_args(inner_expression)
            replacement = f"root(({base_expression}),({degree_expression}))"
            normalized = (
                normalized[:token_index]
                + replacement
                + normalized[close_index + 1:]
            )
    return normalized


def build_allowed_functions(angle_mode):
    return {
        "sin": (lambda value: trig_sin(value, angle_mode), 1),
        "cos": (lambda value: trig_cos(value, angle_mode), 1),
        "tan": (lambda value: trig_tan(value, angle_mode), 1),
        "csc": (lambda value: trig_csc(value, angle_mode), 1),
        "sec": (lambda value: trig_sec(value, angle_mode), 1),
        "cot": (lambda value: trig_cot(value, angle_mode), 1),
        "asin": (lambda value: trig_asin(value, angle_mode), 1),
        "acos": (lambda value: trig_acos(value, angle_mode), 1),
        "atan": (lambda value: trig_atan(value, angle_mode), 1),
        "acsc": (lambda value: trig_acsc(value, angle_mode), 1),
        "asec": (lambda value: trig_asec(value, angle_mode), 1),
        "acot": (lambda value: trig_acot(value, angle_mode), 1),
        "sinh": (math.sinh, 1),
        "cosh": (math.cosh, 1),
        "tanh": (math.tanh, 1),
        "csch": (csch, 1),
        "sech": (sech, 1),
        "coth": (coth, 1),
        "asinh": (math.asinh, 1),
        "acosh": (math.acosh, 1),
        "atanh": (math.atanh, 1),
        "acsch": (acsch, 1),
        "asech": (asech, 1),
        "acoth": (acoth, 1),
        "exp": (math.exp, 1),
        "log10": (math.log10, 1),
        "log": (math.log, 1),
        "sqrt": (math.sqrt, 1),
        "root": (nth_root, 2),
        "abs": (abs, 1),
        "factorial": (safe_factorial, 1),
        "nPr": (safe_perm, 2),
        "nCr": (safe_comb, 2),
        "rand": (random_number, 0)
    }


def evaluate_equation(equation, angle_mode="DEG"):
    if angle_mode not in ("DEG", "RAD"):
        raise ValueError("Invalid angle mode")
    equation = normalize_nth_root_notation(equation)
    equation = equation.replace("π", "pi")
    equation = equation.replace("√", "sqrt")
    equation = equation.replace("log(", "log10(")
    equation = equation.replace("ln(", "log(")
    equation = equation.replace("^", "**")
    allowed_functions = build_allowed_functions(angle_mode)
    parsed = ast.parse(equation, mode="eval")
    return evaluate_node(parsed.body, allowed_functions)


def normalize_programmer_equation(equation, number_base):
    base_value = PROGRAMMER_BASES.get(number_base)
    if base_value is None:
        raise ValueError("Invalid programmer base")

    normalized = equation.upper().strip()
    replacements = [
        ("LSH", "<<"),
        ("RSH", ">>"),
        ("XOR", "^"),
        ("AND", "&"),
        ("OR", "|"),
        ("NOT", "~")
    ]
    for source, target in replacements:
        normalized = normalized.replace(source, target)

    output = []
    index = 0
    while index < len(normalized):
        current = normalized[index]
        if current.isspace():
            index += 1
            continue

        if current.isalnum():
            end = index
            while end < len(normalized) and normalized[end].isalnum():
                end += 1
            token = normalized[index:end]
            converted = int(token, base_value)
            output.append(str(converted))
            index = end
            continue

        two_char_token = normalized[index:index + 2]
        if two_char_token in ("<<", ">>"):
            output.append(two_char_token)
            index += 2
            continue

        if current in "+-*/%()~&|^":
            output.append(current)
            index += 1
            continue

        raise ValueError("Unsupported token")

    return "".join(output)


def normalize_to_word_size(value, word_size):
    if word_size not in PROGRAMMER_WORD_SIZES:
        raise ValueError("Invalid programmer word size")
    mask = (1 << word_size) - 1
    return value & mask


def evaluate_programmer_equation(equation, number_base, word_size=32):
    if word_size not in PROGRAMMER_WORD_SIZES:
        raise ValueError("Invalid programmer word size")
    normalized = normalize_programmer_equation(equation, number_base)
    parsed = ast.parse(normalized, mode="eval")
    return evaluate_programmer_node(parsed.body, word_size)


def evaluate_programmer_node(node, word_size):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return normalize_to_word_size(int(node.value), word_size)

    if isinstance(node, ast.UnaryOp):
        value = evaluate_programmer_node(node.operand, word_size)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return normalize_to_word_size(-value, word_size)
        if isinstance(node.op, ast.Invert):
            return normalize_to_word_size(~value, word_size)
        raise ValueError("Unsupported unary operator")

    if isinstance(node, ast.BinOp):
        left = evaluate_programmer_node(node.left, word_size)
        right = evaluate_programmer_node(node.right, word_size)

        if isinstance(node.op, ast.Add):
            return normalize_to_word_size(left + right, word_size)
        if isinstance(node.op, ast.Sub):
            return normalize_to_word_size(left - right, word_size)
        if isinstance(node.op, ast.Mult):
            return normalize_to_word_size(left * right, word_size)
        if isinstance(node.op, ast.Div):
            return normalize_to_word_size(left // right, word_size)
        if isinstance(node.op, ast.Mod):
            return normalize_to_word_size(left % right, word_size)
        if isinstance(node.op, ast.BitAnd):
            return normalize_to_word_size(left & right, word_size)
        if isinstance(node.op, ast.BitOr):
            return normalize_to_word_size(left | right, word_size)
        if isinstance(node.op, ast.BitXor):
            return normalize_to_word_size(left ^ right, word_size)
        if isinstance(node.op, ast.LShift):
            return normalize_to_word_size(left << right, word_size)
        if isinstance(node.op, ast.RShift):
            return normalize_to_word_size(left >> right, word_size)
        raise ValueError("Unsupported binary operator")

    raise ValueError("Unsupported expression")


def format_programmer_result(value, number_base):
    if number_base == "HEX":
        return format(value, "X")
    if number_base == "BIN":
        return format(value, "b")
    if number_base == "OCT":
        return format(value, "o")
    return str(value)


def evaluate_node(node, allowed_functions):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id == "pi":
            return math.pi
        if node.id == "e":
            return math.e
        raise ValueError("Constant not allowed")

    if isinstance(node, ast.UnaryOp):
        value = evaluate_node(node.operand, allowed_functions)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return -value
        raise ValueError("Unsupported unary operator")

    if isinstance(node, ast.BinOp):
        left = evaluate_node(node.left, allowed_functions)
        right = evaluate_node(node.right, allowed_functions)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise ValueError("Unsupported binary operator")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Unsupported function")
        function_name = node.func.id
        function_config = allowed_functions.get(function_name)
        if function_config is None:
            raise ValueError("Function not allowed")
        function, expected_args = function_config
        if len(node.args) != expected_args:
            raise ValueError("Invalid function arguments")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed")
        evaluated_args = [evaluate_node(arg, allowed_functions) for arg in node.args]
        return function(*evaluated_args)

    raise ValueError("Unsupported expression")


def normalize_result(value):
    if not math.isfinite(value):
        raise ValueError("Non-finite result")
    rounded = round(value, 12)
    if float(rounded).is_integer():
        return int(rounded)
    return rounded


def initialize_database():
    with app.app_context():
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        db.create_all()
        if User.query.filter_by(username="admin").first() is None:
            db.session.add(
                User(
                    username="admin",
                    display_name="Admin",
                    password="123"
                )
            )
            commit_session("initialize_database_admin_seed")


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    initialize_database()
    app.run(debug=app.config["DEBUG"])
    