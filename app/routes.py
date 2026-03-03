from app import db, bcrypt
from flask import url_for, request, flash, redirect
from app.forms import FormCriarConta, FormLogin, FormEditarPerfil
from app.models import User, AuthProvider, UserRole
from flask_login import login_user, logout_user, current_user, login_required
import os
import secrets
from PIL import Image
import uuid
from flask import Blueprint, render_template

main = Blueprint('main', __name__)

# ------------------------
# HOME
# ------------------------

@main.route("/")
def home():
    return render_template("home.html")


# ------------------------
# CADASTRO
# ------------------------

@main.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = FormCriarConta()

    if form.validate_on_submit():
        senha_hash = bcrypt.generate_password_hash(
            form.senha.data
        ).decode("utf-8")

        novo_usuario = User(
            name=form.username.data,
            email=form.email.data,
            password_hash=senha_hash,
            auth_provider=AuthProvider.LOCAL,
            role=UserRole.PLAYER,
        )

        db.session.add(novo_usuario)
        db.session.commit()

        flash("Conta criada com sucesso! Faça login.", "alert-success")
        return redirect(url_for("login"))

    return render_template("cadastro.html", form=form)


# ------------------------
# LOGIN
# ------------------------

@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = FormLogin()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        if (
            user
            and user.auth_provider == AuthProvider.LOCAL
            and bcrypt.check_password_hash(
                user.password_hash, form.senha.data
            )
        ):
            login_user(user, remember=form.lembrar_login.data)

            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("home"))
        else:
            flash("Email ou senha incorretos.", "alert-danger")

    return render_template("login.html", form=form)


# ------------------------
# LOGOUT
# ------------------------

@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado com sucesso.", "alert-success")
    return redirect(url_for("home"))


# ------------------------
# PERFIL
# ------------------------

@main.route("/perfil")
@login_required
def perfil():
    foto = (
        url_for("static", filename=f"fotos_perfil/{current_user.profile_img}")
        if current_user.profile_img
        else url_for("static", filename="fotos_perfil/default.png")
    )
    return render_template("perfil.html", foto_perfil=foto)


# ------------------------
# EDITAR PERFIL
# ------------------------

def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    nome, extensao = os.path.splitext(imagem.filename)
    nome_arquivo = nome + "_" + codigo + extensao

    caminho = os.path.join(app.root_path, "static/fotos_perfil", nome_arquivo)

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
        return redirect(url_for("perfil"))

    elif request.method == "GET":
        form.username.data = current_user.name
        form.email.data = current_user.email

    return render_template("editar_perfil.html", form=form)