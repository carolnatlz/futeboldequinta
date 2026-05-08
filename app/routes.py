import os
import secrets
from datetime import date, datetime, time, timezone
from functools import wraps

from PIL import Image
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from app import bcrypt, db
from app.forms import FormCriarConta, FormEditarPerfil, FormLogin
from app.models import (
    AuthProvider,
    PlayerPosition,
    User,
    UserRole,
)

main = Blueprint("main", __name__)

TEAM_CODES = ("A", "B", "C", "D", "E", "F")
MATCH_SEQUENCE = [
    ("A", "B"),
    ("C", "D"),
    ("E", "F"),
    ("A", "C"),
    ("B", "E"),
    ("D", "F"),
    ("B", "C"),
    ("F", "A"),
    ("E", "D"),
    ("F", "B"),
    ("C", "E"),
    ("D", "A"),
    ("A", "E"),
    ("B", "D"),
    ("C", "F"),
]
WEEKDAY_LABELS = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}
SESSION_START = time(hour=19, minute=0)
SESSION_END = time(hour=22, minute=0)


def roles_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("main.login", next=request.path))

            if current_user.role not in allowed_roles:
                flash("Você não tem permissão para acessar essa área.", "alert-danger")
                return redirect(url_for("main.home"))

            return func(*args, **kwargs)

        return wrapper

    return decorator


def now_utc():
    return datetime.now(timezone.utc)


@main.route("/")
@main.route("/home")
@login_required
def home():
    return render_template("home.html")


@main.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = FormCriarConta()

    if form.validate_on_submit():
        senha_hash = bcrypt.generate_password_hash(form.senha.data).decode("utf-8")
        nome_imagem = salvar_imagem(form.foto_perfil.data)

        novo_usuario = User(
            name=form.username.data,
            email=form.email.data,
            phone=form.celular.data,
            password_hash=senha_hash,
            auth_provider=AuthProvider.LOCAL,
            role=UserRole.PLAYER,
            profile_img=nome_imagem,
            position=PlayerPosition(form.position.data),
            is_active=False,
            is_rejected=False,
        )

        db.session.add(novo_usuario)
        db.session.commit()

        flash("Conta criada com sucesso! Faça login.", "alert-success")
        return redirect(url_for("main.login"))

    return render_template("cadastro.html", form=form)


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = FormLogin()

    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data).first()

        if (
            user
            and user.auth_provider == AuthProvider.LOCAL
            and bcrypt.check_password_hash(user.password_hash, form.senha.data)
        ):
            if user.role == UserRole.PLAYER and not user.is_active:
                flash("Acesso aguardando aprovação.", "alert-warning")
                return redirect(url_for("main.login"))

            login_user(user, remember=form.lembrar_login.data)

            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("main.home"))

        flash("Email ou senha incorretos.", "alert-danger")

    return render_template("login.html", form=form)


@main.route("/admin/aprovacoes")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_aprovacoes():
    pendentes = (
        User.query.filter(
            User.role == UserRole.PLAYER,
            User.is_active.is_(False),
            User.is_rejected.is_(False),
        )
        .order_by(User.created_at.asc())
        .all()
    )
    return render_template("admin_aprovacoes.html", usuarios=pendentes)


@main.route("/admin/rejeitados")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_rejeitados():
    rejeitados = (
        User.query.filter(
            User.role == UserRole.PLAYER,
            User.is_active.is_(False),
            User.is_rejected.is_(True),
        )
        .order_by(User.updated_at.desc())
        .all()
    )
    return render_template("admin_rejeitados.html", usuarios=rejeitados)


@main.route("/admin/aprovacoes/<uuid:user_id>/aceitar", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_aceitar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    usuario.is_active = True
    usuario.is_rejected = False
    usuario.updated_at = now_utc()
    db.session.commit()

    flash(f"Usuário {usuario.name} aprovado com sucesso.", "alert-success")
    return redirect(url_for("main.admin_aprovacoes"))


@main.route("/admin/aprovacoes/<uuid:user_id>/rejeitar", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_rejeitar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    usuario.is_active = False
    usuario.is_rejected = True
    usuario.updated_at = now_utc()
    db.session.commit()

    flash(f"Usuário {usuario.name} movido para rejeitados.", "alert-warning")
    return redirect(url_for("main.admin_rejeitados"))


@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado com sucesso.", "alert-success")
    return redirect(url_for("main.login"))


@main.route("/perfil")
@login_required
def perfil():
    foto = (
        url_for("static", filename=f"fotos_perfil/{current_user.profile_img}")
        if current_user.profile_img
        else url_for("static", filename="fotos_perfil/default.jpg")
    )
    return render_template("perfil.html", foto_perfil=foto)


def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    nome, extensao = os.path.splitext(imagem.filename)
    nome_arquivo = nome + "_" + codigo + extensao

    caminho = os.path.join(current_app.root_path, "static/fotos_perfil", nome_arquivo)

    tamanho = (300, 300)
    img = Image.open(imagem)
    img.thumbnail(tamanho)
    img.save(caminho)

    return nome_arquivo


@main.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    form = FormEditarPerfil()

    if form.validate_on_submit():
        current_user.name = form.username.data
        current_user.email = form.email.data

        if form.foto_perfil.data:
            nome_imagem = salvar_imagem(form.foto_perfil.data)
            current_user.profile_img = nome_imagem

        db.session.commit()

        flash("Perfil atualizado com sucesso!", "alert-success")
        return redirect(url_for("main.perfil"))

    if request.method == "GET":
        form.username.data = current_user.name
        form.email.data = current_user.email

    return render_template("editar_perfil.html", form=form)
