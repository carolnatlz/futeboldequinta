import io
import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from flask import current_app, url_for
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from werkzeug.utils import secure_filename


register_heif_opener()

PROFILE_PHOTO_FOLDER = os.path.join("static", "img", "fotos_perfil")
PROFILE_DEFAULT_FILENAME = "default.jpeg"
PROFILE_THUMBNAIL_SIZE = (800, 800)
REMOTE_URL_SCHEMES = {"http", "https"}
IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}


class ProfileImageUploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadedProfileImage:
    url: str
    public_id: str


def _profile_photos_dir():
    return os.path.join(current_app.root_path, PROFILE_PHOTO_FOLDER)


def _profile_photo_path(filename):
    return os.path.join(_profile_photos_dir(), os.path.basename(filename))


def _default_profile_photo_url():
    return url_for("static", filename=f"img/fotos_perfil/{PROFILE_DEFAULT_FILENAME}")


def _is_remote_url(value):
    if not value:
        return False

    parsed = urlparse(str(value).strip())
    return parsed.scheme in REMOTE_URL_SCHEMES and bool(parsed.netloc)


def profile_photo_url(reference):
    if _is_remote_url(reference):
        return reference

    if reference:
        local_path = _profile_photo_path(reference)
        if os.path.exists(local_path):
            return url_for(
                "static",
                filename=f"img/fotos_perfil/{os.path.basename(reference)}",
            )

    return _default_profile_photo_url()


def _load_cloudinary_sdk():
    try:
        import cloudinary.uploader as uploader
    except ImportError as exc:
        raise ProfileImageUploadError(
            "A biblioteca cloudinary não está instalada neste ambiente."
        ) from exc

    return uploader


def _ensure_cloudinary_ready():
    if not current_app.config.get("CLOUDINARY_ENABLED"):
        raise ProfileImageUploadError(
            "Cloudinary não está configurado para upload de fotos de perfil."
        )


def _normalized_destination_extension(source_extension):
    source_extension = (source_extension or "").lower()
    if source_extension == ".heic":
        return ".jpg"
    return source_extension


def _build_upload_payload(imagem):
    original_name = secure_filename(imagem.filename or "foto_perfil")
    name, source_extension = os.path.splitext(original_name)
    destination_extension = _normalized_destination_extension(source_extension)

    if destination_extension not in IMAGE_FORMATS:
        raise ProfileImageUploadError("Formato de arquivo de imagem não suportado.")

    if not name:
        name = "foto_perfil"

    filename = f"{name}_{secrets.token_hex(8)}{destination_extension}"
    public_id = os.path.splitext(filename)[0]
    image_format = IMAGE_FORMATS[destination_extension]

    source = getattr(imagem, "stream", imagem)
    if hasattr(source, "seek"):
        source.seek(0)

    try:
        with Image.open(source) as image:
            processed = ImageOps.exif_transpose(image)
            if destination_extension in {".jpg", ".jpeg"} and processed.mode != "RGB":
                processed = processed.convert("RGB")
            elif destination_extension == ".png" and processed.mode not in ("RGB", "RGBA", "L"):
                processed = processed.convert("RGBA")

            processed.thumbnail(PROFILE_THUMBNAIL_SIZE)

            payload = io.BytesIO()
            save_kwargs = {"format": image_format}
            if image_format == "JPEG":
                save_kwargs["quality"] = 90
            processed.save(payload, **save_kwargs)
    except OSError as exc:
        raise ProfileImageUploadError("Não foi possível processar a foto enviada.") from exc

    payload.seek(0)
    payload.name = filename
    return payload, public_id


def salvar_imagem(imagem):
    _ensure_cloudinary_ready()
    payload, public_id = _build_upload_payload(imagem)
    uploader = _load_cloudinary_sdk()
    folder = current_app.config.get("CLOUDINARY_PROFILE_IMAGE_FOLDER", "fdq/profile_images")

    try:
        upload_result = uploader.upload(
            payload,
            folder=folder,
            public_id=public_id,
            overwrite=False,
            resource_type="image",
        )
    except Exception as exc:
        raise ProfileImageUploadError(
            "Não foi possível enviar a foto para o Cloudinary."
        ) from exc

    secure_url = upload_result.get("secure_url")
    uploaded_public_id = upload_result.get("public_id")
    if not secure_url or not uploaded_public_id:
        raise ProfileImageUploadError(
            "O Cloudinary não retornou os metadados esperados da imagem."
        )

    return UploadedProfileImage(url=secure_url, public_id=uploaded_public_id)


def remover_imagem(public_id):
    if not public_id:
        return

    try:
        uploader = _load_cloudinary_sdk()
    except ProfileImageUploadError:
        current_app.logger.warning(
            "Cloudinary indisponível para remover avatar antigo %s.", public_id
        )
        return

    try:
        uploader.destroy(public_id, resource_type="image", invalidate=True)
    except Exception:
        current_app.logger.warning(
            "Não foi possível remover a imagem antiga do Cloudinary: %s",
            public_id,
            exc_info=True,
        )
