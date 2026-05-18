from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, login_required, logout_user
from sqlalchemy import func

from app import bcrypt, db
from app.forms import FormCriarConta, FormLogin
from app.models import AccountStatus, AuthProvider, PlayerPosition, User, UserRole

from . import main, salvar_imagem


@main.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("main.nossa_historia"))

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
            account_status=AccountStatus.PENDING,
        )

        db.session.add(novo_usuario)
        db.session.commit()

        flash("Conta criada com sucesso! Faça login.", "alert-success")
        return redirect(url_for("main.login"))

    return render_template("auth/cadastro.html", form=form)


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.nossa_historia"))

    form = FormLogin()

    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data).first()

        if (
            user
            and user.auth_provider == AuthProvider.LOCAL
            and bcrypt.check_password_hash(user.password_hash, form.senha.data)
        ):
            if user.role == UserRole.PLAYER:
                if user.account_status == AccountStatus.PENDING:
                    flash("Seu cadastro ainda está aguardando aprovação.", "alert-warning")
                    return redirect(url_for("main.login"))

                if user.account_status == AccountStatus.REJECTED:
                    flash(
                        "Seu cadastro foi rejeitado. Se achar que houve um engano, entre em contato com a organização.",
                        "alert-danger",
                    )
                    return redirect(url_for("main.login"))

            login_user(user, remember=form.lembrar_login.data)

            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("main.nossa_historia"))

        flash("Email ou senha incorretos.", "alert-danger")

    return render_template("auth/login.html", form=form)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado com sucesso.", "alert-success")
    return redirect(url_for("main.login"))
