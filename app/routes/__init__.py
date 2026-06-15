from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user

from app.profile_images import (
    ProfileImageUploadError,
    profile_photo_url,
    remover_imagem,
    salvar_imagem,
)

main = Blueprint("main", __name__)


def roles_required(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("main.login", next=request.path))

            if current_user.role not in allowed_roles:
                flash("Você não tem permissão para acessar essa área.", "alert-danger")
                return redirect(url_for("main.nossa_historia"))

            return func(*args, **kwargs)

        return wrapper

    return decorator


def now_utc():
    return datetime.now(timezone.utc)


from . import admin_routes, auth_routes, checkin_routes, home_routes, perfil_routes
