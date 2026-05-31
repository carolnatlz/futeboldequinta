import smtplib
import socket
import ssl
import uuid
from email.message import EmailMessage
from urllib.parse import urljoin

from flask import current_app, render_template, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models import AuthProvider, User


EMAIL_VERIFICATION_SALT = "fdq-email-verification"
PASSWORD_RESET_SALT = "fdq-password-reset"


class EmailDeliveryError(RuntimeError):
    pass


class TokenValidationError(RuntimeError):
    pass


class TokenExpiredError(TokenValidationError):
    pass


def generate_email_verification_token(user):
    return _serializer().dumps(
        {"user_id": str(user.id), "email": user.email},
        salt=EMAIL_VERIFICATION_SALT,
    )


def read_email_verification_token(token):
    payload = _loads_token(
        token,
        EMAIL_VERIFICATION_SALT,
        current_app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE"],
    )
    return _resolve_email_verification_user(payload)


def generate_password_reset_token(user):
    return _serializer().dumps(
        {"user_id": str(user.id), "password_hash": user.password_hash or ""},
        salt=PASSWORD_RESET_SALT,
    )


def read_password_reset_token(token):
    payload = _loads_token(
        token,
        PASSWORD_RESET_SALT,
        current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"],
    )
    return _resolve_password_reset_user(payload)


def send_email_verification_email(user):
    verify_link = build_public_url("main.verificar_email", token=generate_email_verification_token(user))
    _send_smtp_email(
        to_email=user.email,
        subject="Confirme seu email no Futebol de Quinta",
        html=render_template(
            "emails/verificar_email.html",
            user=user,
            verify_link=verify_link,
            expiration_minutes=_token_minutes(
                current_app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE"]
            ),
        ),
        text=render_template(
            "emails/verificar_email.txt",
            user=user,
            verify_link=verify_link,
            expiration_minutes=_token_minutes(
                current_app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE"]
            ),
        ),
    )


def send_password_reset_email(user):
    reset_link = build_public_url("main.redefinir_senha", token=generate_password_reset_token(user))
    _send_smtp_email(
        to_email=user.email,
        subject="Redefina sua senha no Futebol de Quinta",
        html=render_template(
            "emails/redefinir_senha.html",
            user=user,
            reset_link=reset_link,
            expiration_minutes=_token_minutes(
                current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"]
            ),
        ),
        text=render_template(
            "emails/redefinir_senha.txt",
            user=user,
            reset_link=reset_link,
            expiration_minutes=_token_minutes(
                current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"]
            ),
        ),
    )


def build_public_url(endpoint, **values):
    public_base_url = current_app.config.get("PUBLIC_BASE_URL")
    if public_base_url:
        path = url_for(endpoint, **values)
        return urljoin(f"{public_base_url.rstrip('/')}/", path.lstrip("/"))
    return url_for(endpoint, _external=True, **values)


def _serializer():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY não configurada para assinar tokens.")
    return URLSafeTimedSerializer(secret_key)


def _loads_token(token, salt, max_age):
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age)
    except SignatureExpired as exc:
        raise TokenExpiredError("O link expirou.") from exc
    except BadSignature as exc:
        raise TokenValidationError("O link é inválido.") from exc


def _resolve_email_verification_user(payload):
    user = _get_user_by_token_id(payload.get("user_id"))
    if not user or user.auth_provider != AuthProvider.LOCAL:
        raise TokenValidationError("Conta inválida para verificação.")
    if user.email != payload.get("email"):
        raise TokenValidationError("Esse link não corresponde mais ao email atual.")
    return user


def _resolve_password_reset_user(payload):
    user = _get_user_by_token_id(payload.get("user_id"))
    if not user or user.auth_provider != AuthProvider.LOCAL:
        raise TokenValidationError("Conta inválida para redefinição.")
    if (user.password_hash or "") != payload.get("password_hash", ""):
        raise TokenValidationError("Esse link de redefinição não é mais válido.")
    return user


def _send_smtp_email(*, to_email, subject, html, text):
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")
    default_sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    mail_port = current_app.config.get("MAIL_PORT")
    mail_use_tls = current_app.config.get("MAIL_USE_TLS")
    mail_use_ssl = current_app.config.get("MAIL_USE_SSL")
    mail_timeout = current_app.config.get("MAIL_TIMEOUT", 10)
    if not mail_server or not mail_username or not mail_password or not default_sender:
        raise EmailDeliveryError(
            "Configuração SMTP incompleta. Defina MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD e MAIL_DEFAULT_SENDER."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = default_sender
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        if mail_use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                mail_server,
                mail_port,
                timeout=mail_timeout,
                context=context,
            ) as smtp:
                smtp.login(mail_username, mail_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(mail_server, mail_port, timeout=mail_timeout) as smtp:
                smtp.ehlo()
                if mail_use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(mail_username, mail_password)
                smtp.send_message(message)
    except (smtplib.SMTPException, socket.timeout, TimeoutError, OSError, ssl.SSLError) as exc:
        current_app.logger.error("Falha ao enviar email por SMTP: %s", exc)
        raise EmailDeliveryError("Não foi possível enviar o email por SMTP.") from exc


def _token_minutes(max_age_seconds):
    return max(1, round(max_age_seconds / 60))


def _get_user_by_token_id(user_id):
    try:
        normalized_id = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        raise TokenValidationError("Identificador de usuário inválido.")
    return User.query.get(normalized_id)
