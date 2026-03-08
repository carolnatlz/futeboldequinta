import os
import uuid

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail

# =========================
# Extensões (SEM app ainda)
# =========================
db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()

# =========================
# Application Factory
# =========================
def create_app():

    # Carregar .env apenas local
    if os.environ.get("RENDER") is None:
        from dotenv import load_dotenv
        load_dotenv()

    app = Flask(__name__)

    # =========================
    # Configurações
    # =========================
    app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada.")

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # =========================
    # Inicializar extensões
    # =========================
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)

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
