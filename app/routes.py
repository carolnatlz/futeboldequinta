from app import db, bcrypt
from flask import url_for, request, flash, redirect, current_app
from app.forms import FormCriarConta, FormLogin, FormEditarPerfil
from app.models import User, AuthProvider, UserRole, PlayerPosition
from flask_login import login_user, logout_user, current_user, login_required
import os
import secrets
from PIL import Image
import uuid
from flask import Blueprint, render_template
from functools import wraps
from datetime import datetime, timezone
from sqlalchemy import func

main = Blueprint('main', __name__)


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

# ------------------------
# HOME
# ------------------------

@main.route("/")
@main.route("/home")
def home():
    return render_template("home.html")


# ------------------------
# CADASTRO
# ------------------------

@main.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = FormCriarConta()

    if form.validate_on_submit():
        senha_hash = bcrypt.generate_password_hash(
            form.senha.data
        ).decode("utf-8")

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


# ------------------------
# LOGIN
# ------------------------

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
            and bcrypt.check_password_hash(
                user.password_hash, form.senha.data
            )
        ):
            if user.role == UserRole.PLAYER and not user.is_active:
                flash("Acesso aguardando aprovação.", "alert-warning")
                return redirect(url_for("main.login"))

            login_user(user, remember=form.lembrar_login.data)

            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("main.home"))
        else:
            flash("Email ou senha incorretos.", "alert-danger")

    return render_template("login.html", form=form)


# ------------------------
# APROVAÇÕES ADMIN
# ------------------------

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
    usuario.updated_at = datetime.now(timezone.utc)
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
    usuario.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f"Usuário {usuario.name} movido para rejeitados.", "alert-warning")
    return redirect(url_for("main.admin_rejeitados"))


# ------------------------
# LOGOUT
# ------------------------

@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado com sucesso.", "alert-success")
    return redirect(url_for("main.home"))


# ------------------------
# PERFIL
# ------------------------

@main.route("/perfil")
@login_required
def perfil():
    foto = (
        url_for("static", filename=f"fotos_perfil/{current_user.profile_img}")
        if current_user.profile_img
        else url_for("static", filename="fotos_perfil/default.jpg")
    )
    return render_template("perfil.html", foto_perfil=foto)


# ------------------------
# EDITAR PERFIL
# ------------------------

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

    elif request.method == "GET":
        form.username.data = current_user.name
        form.email.data = current_user.email

    return render_template("editar_perfil.html", form=form)
