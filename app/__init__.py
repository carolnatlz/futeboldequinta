import os
import uuid

from dotenv import load_dotenv
from flask import Flask, url_for
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from app.profile_images import profile_photo_url

# =========================
# Extensões (SEM app ainda)
# =========================
db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
login_manager = LoginManager()

# =========================
# Application Factory
# =========================
def create_app():
    load_dotenv()
    app = Flask(__name__)

    # =========================
    # Configurações
    # =========================
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SQLALCHEMY_DATABASE_URI")
    )
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL (ou SQLALCHEMY_DATABASE_URI) não configurada no ambiente."
        )

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config["RESEND_API_KEY"] = os.environ.get("RESEND_API_KEY")
    app.config["RESEND_FROM_EMAIL"] = os.environ.get("RESEND_FROM_EMAIL")
    app.config["RESEND_REPLY_TO"] = os.environ.get("RESEND_REPLY_TO")
    app.config["RESEND_TIMEOUT"] = int(os.environ.get("RESEND_TIMEOUT", 10))
    app.config["PUBLIC_BASE_URL"] = os.environ.get("PUBLIC_BASE_URL")
    app.config["CLOUDINARY_CLOUD_NAME"] = os.environ.get("CLOUDINARY_CLOUD_NAME")
    app.config["CLOUDINARY_API_KEY"] = os.environ.get("CLOUDINARY_API_KEY")
    app.config["CLOUDINARY_API_SECRET"] = os.environ.get("CLOUDINARY_API_SECRET")
    app.config["CLOUDINARY_PROFILE_IMAGE_FOLDER"] = os.environ.get(
        "CLOUDINARY_PROFILE_IMAGE_FOLDER",
        "fdq/profile_images",
    )
    app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE"] = int(
        os.environ.get("EMAIL_VERIFICATION_TOKEN_MAX_AGE", 60 * 60 * 24)
    )
    app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] = int(
        os.environ.get("PASSWORD_RESET_TOKEN_MAX_AGE", 60 * 60)
    )
    app.config["EMAIL_VERIFICATION_COOLDOWN_SECONDS"] = int(
        os.environ.get("EMAIL_VERIFICATION_COOLDOWN_SECONDS", 60)
    )

    cloudinary_config = {
        "cloud_name": app.config["CLOUDINARY_CLOUD_NAME"],
        "api_key": app.config["CLOUDINARY_API_KEY"],
        "api_secret": app.config["CLOUDINARY_API_SECRET"],
        "secure": True,
    }
    app.config["CLOUDINARY_ENABLED"] = False
    if all(
        (
            cloudinary_config["cloud_name"],
            cloudinary_config["api_key"],
            cloudinary_config["api_secret"],
        )
    ):
        try:
            import cloudinary
        except ImportError:
            app.logger.warning(
                "Cloudinary SDK não está instalada neste ambiente; uploads de foto ficarão indisponíveis."
            )
        else:
            cloudinary.config(**cloudinary_config)
            app.config["CLOUDINARY_ENABLED"] = True
    elif any(
        (
            cloudinary_config["cloud_name"],
            cloudinary_config["api_key"],
            cloudinary_config["api_secret"],
        )
    ):
        app.logger.warning(
            "Cloudinary está configurado parcialmente; uploads de foto ficarão indisponíveis."
        )

    # =========================
    # Inicializar extensões
    # =========================
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # =========================
    # Config Login
    # =========================
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Quer ver o que está no site? primeiro faça seu cadastro ou login'
    login_manager.login_message_category = 'alert-info'

    # =========================
    # User Loader
    # =========================
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(uuid.UUID(user_id))

    @app.context_processor
    def inject_asset_url():
        def asset_url(filename):
            asset_path = os.path.join(app.static_folder, filename)

            if os.path.exists(asset_path):
                version = int(os.path.getmtime(asset_path))
                return url_for("static", filename=filename, v=version)

            return url_for("static", filename=filename)

        return {
            "asset_url": asset_url,
            "profile_photo_url": profile_photo_url,
        }

    # =========================
    # Registrar rotas
    # =========================
    from app.routes import main
    app.register_blueprint(main)

    return app
