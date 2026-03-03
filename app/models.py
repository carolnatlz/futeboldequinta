from email.policy import default
from enum import unique
from app import db
from datetime import datetime
from flask_login import UserMixin
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from app import db
import enum
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

# -------------------------
# ENUMS (Tabelas de domínio)
# -------------------------

class AuthProvider(enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"

class UserRole(enum.Enum):
    ADMIN = "admin"
    PLAYER = "player"
    ORGANIZER = "organizer"

class PlayerPosition(enum.Enum):
    GOL = "gol"
    ATAQUE = "ataque"
    DEFESA = "defesa"

# -------------------------
# USER MODEL
# -------------------------

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    name = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    auth_provider = db.Column(
        db.Enum(AuthProvider, name="auth_provider_enum"),
        nullable=False
    )
    role = db.Column(
        db.Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.PLAYER
    )
    position = db.Column(
        db.Enum(PlayerPosition, name="player_position_enum"),
        nullable=True
    )
    profile_img = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True),server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True),server_default=func.now(),onupdate=func.now())
    phone = db.Column(db.String(20), unique=True, nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"