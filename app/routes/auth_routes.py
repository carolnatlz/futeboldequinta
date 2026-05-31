from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, login_required, logout_user
from sqlalchemy import func

from app import bcrypt, db
from app.email_auth import (
    EmailDeliveryError,
    TokenExpiredError,
    TokenValidationError,
    read_email_verification_token,
    read_password_reset_token,
    send_email_verification_email,
    send_password_reset_email,
)
from app.forms import (
    FormCriarConta,
    FormLogin,
    FormRedefinirSenha,
    FormReenviarVerificacao,
    FormSolicitarRedefinicaoSenha,
)
from app.models import AccountStatus, AuthProvider, PlayerPosition, User, UserRole

from . import main, now_utc, salvar_imagem


def _send_verification_email_with_tracking(user):
    send_email_verification_email(user)
    user.email_verification_sent_at = now_utc()
    db.session.commit()


def _send_password_reset_email_safely(user):
    send_password_reset_email(user)


def _verification_cooldown_remaining(user):
    sent_at = user.email_verification_sent_at
    if not sent_at:
        return 0

    cooldown_seconds = current_app.config["EMAIL_VERIFICATION_COOLDOWN_SECONDS"]
    elapsed_seconds = int((now_utc() - sent_at).total_seconds())
    return max(0, cooldown_seconds - elapsed_seconds)


def _handle_verification_email_send(user, success_message, *, warning_message=None):
    try:
        _send_verification_email_with_tracking(user)
    except EmailDeliveryError:
        db.session.rollback()
        flash(
            warning_message
            or (
                "Sua conta foi salva, mas não conseguimos enviar o email de verificação agora. "
                "Tente novamente em instantes."
            ),
            "alert-warning",
        )
    else:
        flash(success_message, "alert-success")


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

        _handle_verification_email_send(
            novo_usuario,
            "Conta criada com sucesso! Enviamos um link de verificação para seu email.",
        )
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
            and user.password_hash
            and bcrypt.check_password_hash(user.password_hash, form.senha.data)
        ):
            if not user.email_verified_at:
                flash(
                    "Seu email ainda não foi verificado. Confira sua caixa de entrada ou solicite um novo link de verificação.",
                    "alert-warning",
                )
                return redirect(
                    url_for("main.reenviar_verificacao_email", email=user.email)
                )

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


@main.route("/verificar-email/<token>")
def verificar_email(token):
    if current_user.is_authenticated:
        logout_user()

    try:
        user = read_email_verification_token(token)
    except TokenExpiredError:
        flash(
            "Esse link de verificação expirou. Solicite um novo link para continuar.",
            "alert-warning",
        )
        return redirect(url_for("main.reenviar_verificacao_email"))
    except TokenValidationError:
        flash(
            "Esse link de verificação é inválido ou não corresponde mais ao email atual.",
            "alert-danger",
        )
        return redirect(url_for("main.reenviar_verificacao_email"))

    if user.email_verified_at:
        flash("Esse email já foi verificado. Você já pode entrar.", "alert-info")
        return redirect(url_for("main.login"))

    user.email_verified_at = now_utc()
    db.session.commit()

    if user.account_status == AccountStatus.PENDING:
        flash(
            "Email verificado com sucesso! Agora falta apenas a aprovação do seu cadastro pela organização.",
            "alert-success",
        )
    else:
        flash("Email verificado com sucesso! Agora você já pode entrar.", "alert-success")

    return redirect(url_for("main.login"))


@main.route("/verificacao-email/reenviar", methods=["GET", "POST"])
def reenviar_verificacao_email():
    form = FormReenviarVerificacao()
    if request.method == "GET":
        if request.args.get("email"):
            form.email.data = request.args.get("email", "").strip().lower()
        elif current_user.is_authenticated:
            form.email.data = (current_user.email or "").strip().lower()

    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data).first()
        if user and user.auth_provider == AuthProvider.LOCAL and not user.email_verified_at:
            cooldown_remaining = _verification_cooldown_remaining(user)
            if cooldown_remaining > 0:
                flash(
                    f"Acabamos de enviar um link. Aguarde {cooldown_remaining} segundo(s) para solicitar outro.",
                    "alert-info",
                )
                return redirect(
                    url_for("main.reenviar_verificacao_email", email=form.email.data)
                )

            _handle_verification_email_send(
                user,
                "Enviamos um novo link de verificação para o seu email.",
                warning_message=(
                    "Encontramos sua conta, mas não conseguimos reenviar o email agora. "
                    "Tente novamente em instantes."
                ),
            )
            return redirect(url_for("main.login"))

        flash(
            "Se existir uma conta pendente de verificação com esse email, enviaremos um novo link.",
            "alert-info",
        )
        return redirect(url_for("main.login"))

    return render_template("auth/reenviar_verificacao.html", form=form)


@main.route("/senha/esqueci", methods=["GET", "POST"])
def solicitar_redefinicao_senha():
    if current_user.is_authenticated:
        return redirect(url_for("main.nossa_historia"))

    form = FormSolicitarRedefinicaoSenha()

    if form.validate_on_submit():
        user = User.query.filter(func.lower(User.email) == form.email.data).first()
        if (
            user
            and user.auth_provider == AuthProvider.LOCAL
            and user.email_verified_at
        ):
            try:
                _send_password_reset_email_safely(user)
            except EmailDeliveryError:
                current_app.logger.exception(
                    "Falha ao enviar email de redefinição para %s", user.email
                )

        flash(
            "Se existir uma conta verificada com esse email, enviaremos um link para redefinição de senha.",
            "alert-info",
        )
        return redirect(url_for("main.login"))

    return render_template("auth/solicitar_redefinicao_senha.html", form=form)


@main.route("/senha/redefinir/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    if current_user.is_authenticated:
        logout_user()

    try:
        user = read_password_reset_token(token)
    except TokenExpiredError:
        flash(
            "Esse link de redefinição expirou. Solicite um novo email para continuar.",
            "alert-warning",
        )
        return redirect(url_for("main.solicitar_redefinicao_senha"))
    except TokenValidationError:
        flash(
            "Esse link de redefinição é inválido ou já foi substituído por um mais novo.",
            "alert-danger",
        )
        return redirect(url_for("main.solicitar_redefinicao_senha"))

    form = FormRedefinirSenha()

    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.senha.data).decode("utf-8")
        db.session.commit()
        flash("Sua senha foi atualizada com sucesso. Agora você já pode entrar.", "alert-success")
        return redirect(url_for("main.login"))

    return render_template("auth/redefinir_senha.html", form=form)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logout realizado com sucesso.", "alert-success")
    return redirect(url_for("main.login"))
