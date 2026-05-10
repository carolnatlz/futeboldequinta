import os
import secrets
from datetime import datetime, timezone
from functools import wraps

from PIL import Image
from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from pillow_heif import register_heif_opener

main = Blueprint("main", __name__)

register_heif_opener()


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
    nome_original = secure_filename(imagem.filename or "foto_perfil")
    nome, extensao = os.path.splitext(nome_original)
    extensao = extensao.lower()

    # Converte HEIC para JPG para manter compatibilidade de exibicao no navegador.
    extensao_destino = ".jpg" if extensao == ".heic" else extensao
    nome_arquivo = nome + "_" + codigo + extensao_destino

    caminho = os.path.join(
        current_app.root_path,
        "static/img/fotos_perfil",
        nome_arquivo,
    )

    tamanho = (300, 300)
    img = Image.open(imagem)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail(tamanho)
    if extensao_destino == ".jpg":
        img.save(caminho, format="JPEG", quality=90)
    else:
        img.save(caminho)

    return nome_arquivo


from . import admin_routes, auth_routes, home_routes, perfil_routes
