import os
import uuid
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate

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
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = (
        os.environ.get("MAIL_USE_TLS", "true").strip().lower() == "true"
    )
    app.config["MAIL_USE_SSL"] = (
        os.environ.get("MAIL_USE_SSL", "false").strip().lower() == "true"
    )
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")
    app.config["MAIL_TIMEOUT"] = int(os.environ.get("MAIL_TIMEOUT", 10))
    app.config["PUBLIC_BASE_URL"] = os.environ.get("PUBLIC_BASE_URL")
    app.config["EMAIL_VERIFICATION_TOKEN_MAX_AGE"] = int(
        os.environ.get("EMAIL_VERIFICATION_TOKEN_MAX_AGE", 60 * 60 * 24)
    )
    app.config["PASSWORD_RESET_TOKEN_MAX_AGE"] = int(
        os.environ.get("PASSWORD_RESET_TOKEN_MAX_AGE", 60 * 60)
    )
    app.config["EMAIL_VERIFICATION_COOLDOWN_SECONDS"] = int(
        os.environ.get("EMAIL_VERIFICATION_COOLDOWN_SECONDS", 60)
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

    # =========================
    # Registrar rotas
    # =========================
    from app.routes import main
    app.register_blueprint(main)

    return app
