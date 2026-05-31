import smtplib
import socket
import ssl
import uuid
from email.message import EmailMessage
from urllib.parse import urljoin

from flask import current_app, has_app_context, render_template, url_for
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


class ConfiguredSMTP(smtplib.SMTP):
    def __init__(self, *args, ip_family="auto", **kwargs):
        self.ip_family = ip_family
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        return _create_socket_connection(
            host,
            port,
            timeout,
            family_preference=self.ip_family,
        )


class ConfiguredSMTP_SSL(smtplib.SMTP_SSL):
    def __init__(self, *args, ip_family="auto", **kwargs):
        self.ip_family = ip_family
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        raw_socket = _create_socket_connection(
            host,
            port,
            timeout,
            family_preference=self.ip_family,
        )
        if self.context is None:
            self.context = ssl.create_default_context()
        return self.context.wrap_socket(raw_socket, server_hostname=self._host)


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
    mail_ip_family = current_app.config.get("MAIL_IP_FAMILY", "auto")
    mail_timeout = current_app.config.get("MAIL_TIMEOUT", 10)
    if not mail_server or not mail_username or not mail_password or not default_sender:
        raise EmailDeliveryError(
            "Configuração SMTP incompleta. Defina MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD e MAIL_DEFAULT_SENDER."
        )

    logger = current_app.logger

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = default_sender
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        if mail_use_ssl:
            logger.info(
                "SMTP 1 - abrindo conexão SSL com %s:%s para %s (family=%s timeout=%ss)",
                mail_server,
                mail_port,
                to_email,
                mail_ip_family,
                mail_timeout,
            )
            context = ssl.create_default_context()
            with ConfiguredSMTP_SSL(
                mail_server,
                mail_port,
                timeout=mail_timeout,
                context=context,
                ip_family=mail_ip_family,
            ) as smtp:
                logger.info("SMTP 2 - conectado via SSL")
                smtp.login(mail_username, mail_password)
                logger.info("SMTP 3 - autenticado")
                smtp.send_message(message)
                logger.info("SMTP 4 - email enviado para %s", to_email)
        else:
            logger.info(
                "SMTP 1 - abrindo conexão com %s:%s para %s (tls=%s family=%s timeout=%ss)",
                mail_server,
                mail_port,
                to_email,
                mail_use_tls,
                mail_ip_family,
                mail_timeout,
            )
            with ConfiguredSMTP(
                mail_server,
                mail_port,
                timeout=mail_timeout,
                ip_family=mail_ip_family,
            ) as smtp:
                logger.info("SMTP 2 - conectado")
                smtp.ehlo()
                if mail_use_tls:
                    logger.info("SMTP 2.1 - iniciando STARTTLS")
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    logger.info("SMTP 2.2 - STARTTLS concluído")
                smtp.login(mail_username, mail_password)
                logger.info("SMTP 3 - autenticado")
                smtp.send_message(message)
                logger.info("SMTP 4 - email enviado para %s", to_email)
    except (smtplib.SMTPException, socket.timeout, TimeoutError, OSError, ssl.SSLError) as exc:
        logger.exception(
            "Falha SMTP ao enviar email para %s via %s:%s",
            to_email,
            mail_server,
            mail_port,
        )
        raise EmailDeliveryError("Não foi possível enviar o email por SMTP.") from exc


def _token_minutes(max_age_seconds):
    return max(1, round(max_age_seconds / 60))


def _get_user_by_token_id(user_id):
    try:
        normalized_id = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        raise TokenValidationError("Identificador de usuário inválido.")
    return User.query.get(normalized_id)


def _create_socket_connection(host, port, timeout, *, family_preference="auto"):
    family = _resolve_address_family(family_preference)
    addresses = socket.getaddrinfo(
        host,
        port,
        family=family,
        type=socket.SOCK_STREAM,
    )
    logger = _socket_logger()
    if logger is not None:
        logger.info(
            "SMTP DNS - %s:%s resolvido para %s endereco(s) usando family=%s",
            host,
            port,
            len(addresses),
            family_preference,
        )
    last_error = None
    for index, (resolved_family, socktype, proto, _, sockaddr) in enumerate(addresses, start=1):
        sock = None
        try:
            if logger is not None:
                logger.info(
                    "SMTP socket - tentativa %s para %s",
                    index,
                    _format_sockaddr(sockaddr),
                )
            sock = socket.socket(resolved_family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            sock.connect(sockaddr)
            if logger is not None:
                logger.info(
                    "SMTP socket - conexao TCP estabelecida em %s",
                    _format_sockaddr(sockaddr),
                )
            return sock
        except OSError as exc:
            last_error = exc
            if logger is not None:
                logger.warning(
                    "SMTP socket - tentativa %s falhou para %s: %s",
                    index,
                    _format_sockaddr(sockaddr),
                    exc,
                )
            if sock is not None:
                sock.close()

    if last_error is not None:
        raise last_error
    raise OSError(
        f"Nenhum endereço disponível para {host}:{port} com family={family_preference}"
    )


def _resolve_address_family(family_preference):
    normalized_family = (family_preference or "auto").strip().lower()
    if normalized_family == "auto":
        return socket.AF_UNSPEC
    if normalized_family == "ipv4":
        return socket.AF_INET
    if normalized_family == "ipv6":
        return socket.AF_INET6
    raise ValueError(
        "MAIL_IP_FAMILY inválido. Use 'auto', 'ipv4' ou 'ipv6'."
    )


def _socket_logger():
    if has_app_context():
        return current_app.logger
    return None


def _format_sockaddr(sockaddr):
    if isinstance(sockaddr, tuple):
        if len(sockaddr) >= 2:
            return f"{sockaddr[0]}:{sockaddr[1]}"
        return str(sockaddr[0])
    return str(sockaddr)
