import os
import secrets
from datetime import datetime, timezone
from functools import wraps

from PIL import Image
from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user

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


def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    nome, extensao = os.path.splitext(imagem.filename)
    nome_arquivo = nome + "_" + codigo + extensao

    caminho = os.path.join(
        current_app.root_path,
        "static/img/fotos_perfil",
        nome_arquivo,
    )

    tamanho = (300, 300)
    img = Image.open(imagem)
    img.thumbnail(tamanho)
    img.save(caminho)

    return nome_arquivo


from . import admin_routes, auth_routes, home_routes, perfil_routes
