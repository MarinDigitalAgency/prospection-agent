"""Blueprint d'authentification — login, register, logout."""

from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

from db import create_user, get_user_by_email, verify_password

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_email" in session:
        return redirect("/")

    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if verify_password(email, password):
            session["user_email"] = email.lower()
            session.permanent = True
            return redirect(request.args.get("next") or "/")
        error = "Email ou mot de passe incorrect."

    return render_template("login.html", mode="login", error=error)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_email" in session:
        return redirect("/")

    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        if not email or "@" not in email:
            error = "Adresse email invalide."
        elif len(password) < 8:
            error = "Le mot de passe doit contenir au moins 8 caractères."
        elif password != confirm:
            error = "Les mots de passe ne correspondent pas."
        elif get_user_by_email(email):
            error = "Cette adresse email est déjà utilisée."
        else:
            create_user(email, password)
            session["user_email"] = email.lower()
            session.permanent = True
            return redirect("/")

    return render_template("login.html", mode="register", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
