import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from flask import current_app, render_template, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models import AuthProvider, User


EMAIL_VERIFICATION_SALT = "fdq-email-verification"
PASSWORD_RESET_SALT = "fdq-password-reset"
RESEND_SEND_EMAIL_URL = "https://api.resend.com/emails"


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
    verify_link = build_public_url(
        "main.verificar_email",
        token=generate_email_verification_token(user),
    )
    _send_resend_email(
        to_email=user.email,
        subject="Confirme seu email do Futebol de Quinta",
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
        tags=[{"name": "category", "value": "confirm_email"}],
    )


def send_password_reset_email(user):
    reset_link = build_public_url(
        "main.redefinir_senha",
        token=generate_password_reset_token(user),
    )
    _send_resend_email(
        to_email=user.email,
        subject="Redefina sua senha do Futebol de Quinta",
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
        tags=[{"name": "category", "value": "password_reset"}],
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


def _send_resend_email(*, to_email, subject, html, text, tags=None):
    api_key = current_app.config.get("RESEND_API_KEY")
    from_email = current_app.config.get("RESEND_FROM_EMAIL")
    reply_to = current_app.config.get("RESEND_REPLY_TO")
    timeout = current_app.config.get("RESEND_TIMEOUT", 10)

    if not api_key or not from_email:
        raise EmailDeliveryError(
            "Configuração Resend incompleta. Defina RESEND_API_KEY e RESEND_FROM_EMAIL."
        )

    logger = current_app.logger
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if tags:
        payload["tags"] = tags

    logger.info(
        "Resend 1 - enviando email para %s com timeout=%ss",
        to_email,
        timeout,
    )

    request = Request(
        RESEND_SEND_EMAIL_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # A documentacao da API exige User-Agent em chamadas HTTP diretas.
            "User-Agent": "FutebolDeQuinta/1.0",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode("utf-8")
            parsed_response = json.loads(raw_response) if raw_response else {}
            email_id = parsed_response.get("id")
            logger.info(
                "Resend 2 - email enviado para %s com id=%s",
                to_email,
                email_id or "desconhecido",
            )
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception(
            "Falha Resend ao enviar email para %s: status=%s body=%s",
            to_email,
            exc.code,
            _truncate_for_log(error_body),
        )
        raise EmailDeliveryError("Nao foi possivel enviar o email via Resend.") from exc
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        logger.exception("Falha Resend ao enviar email para %s", to_email)
        raise EmailDeliveryError("Nao foi possivel enviar o email via Resend.") from exc


def _truncate_for_log(value, limit=500):
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."


def _token_minutes(max_age_seconds):
    return max(1, round(max_age_seconds / 60))


def _get_user_by_token_id(user_id):
    try:
        normalized_id = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        raise TokenValidationError("Identificador de usuario invalido.")
    return User.query.get(normalized_id)
