import os
import secrets
from datetime import datetime, timezone
from functools import wraps

from PIL import Image, ImageOps
from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from pillow_heif import register_heif_opener

main = Blueprint("main", __name__)

register_heif_opener()

PROFILE_PHOTO_FOLDER = os.path.join("static", "img", "fotos_perfil")
PROFILE_SHIELD_VARIANT_SUFFIX = "_shield_profile"
PROFILE_SHIELD_CANVAS_SIZE = (708, 804)
PROFILE_SHIELD_IMAGE_BOX_RATIO = 0.52


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


def _profile_photos_dir():
    return os.path.join(current_app.root_path, PROFILE_PHOTO_FOLDER)


def _profile_photo_path(filename):
    return os.path.join(_profile_photos_dir(), filename)


def _shield_variant_filename(filename):
    nome, _ = os.path.splitext(filename)
    return f"{nome}{PROFILE_SHIELD_VARIANT_SUFFIX}.png"


def _build_shield_profile_variant(source_path, target_path):
    canvas_width, canvas_height = PROFILE_SHIELD_CANVAS_SIZE
    max_image_width = int(canvas_width * PROFILE_SHIELD_IMAGE_BOX_RATIO)
    max_image_height = int(canvas_height * PROFILE_SHIELD_IMAGE_BOX_RATIO)
    resampling = getattr(Image, "Resampling", Image).LANCZOS

    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        target_box = (
            min(max_image_width, image.width),
            min(max_image_height, image.height),
        )
        contained = ImageOps.contain(
            image,
            target_box,
            method=resampling,
        )

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    offset_x = (canvas_width - contained.width) // 2
    offset_y = (canvas_height - contained.height) // 2
    canvas.alpha_composite(contained, (offset_x, offset_y))
    canvas.save(target_path, format="PNG")


def ensure_shield_profile_variant(filename):
    source_filename = filename or "default.jpeg"
    source_path = _profile_photo_path(source_filename)
    if not os.path.exists(source_path):
        return source_filename

    variant_filename = _shield_variant_filename(source_filename)
    variant_path = _profile_photo_path(variant_filename)

    if not os.path.exists(variant_path):
        try:
            _build_shield_profile_variant(source_path, variant_path)
        except OSError:
            return source_filename

    return variant_filename


def profile_shield_photo_url(filename):
    variant_filename = ensure_shield_profile_variant(filename)
    return url_for("static", filename=f"img/fotos_perfil/{variant_filename}")


def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    nome_original = secure_filename(imagem.filename or "foto_perfil")
    nome, extensao = os.path.splitext(nome_original)
    extensao = extensao.lower()

    # Converte HEIC para JPG para manter compatibilidade de exibicao no navegador.
    extensao_destino = ".jpg" if extensao == ".heic" else extensao
    nome_arquivo = nome + "_" + codigo + extensao_destino

    caminho = _profile_photo_path(nome_arquivo)

    tamanho = (300, 300)
    img = Image.open(imagem)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail(tamanho)
    if extensao_destino == ".jpg":
        img.save(caminho, format="JPEG", quality=90)
    else:
        img.save(caminho)

    ensure_shield_profile_variant(nome_arquivo)

    return nome_arquivo


from . import admin_routes, auth_routes, checkin_routes, home_routes, perfil_routes
