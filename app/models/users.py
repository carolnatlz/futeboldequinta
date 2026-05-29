import enum
import uuid

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app import db


class AuthProvider(enum.Enum):
    LOCAL = "local"
    GOOGLE = "google"


class UserRole(enum.Enum):
    ADMIN = "admin"
    PLAYER = "player"
    ORGANIZER = "organizer"


class AccountStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PlayerPosition(enum.Enum):
    GOL = "gol"
    ATAQUE = "ataque"
    DEFESA = "defesa"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    auth_provider = db.Column(
        db.Enum(AuthProvider, name="auth_provider_enum"),
        nullable=False,
    )
    role = db.Column(
        db.Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.PLAYER,
    )
    position = db.Column(
        db.Enum(PlayerPosition, name="player_position_enum"),
        nullable=True,
    )
    profile_img = db.Column(db.String(255), nullable=True)
    account_status = db.Column(
        db.Enum(AccountStatus, name="account_status_enum"),
        nullable=False,
        default=AccountStatus.PENDING,
    )
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    phone = db.Column(db.String(20), unique=True, nullable=True)

    checkins = db.relationship(
        "GameCheckin",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy=True,
        foreign_keys="GameCheckin.user_id",
    )
    updated_checkins = db.relationship(
        "GameCheckin",
        foreign_keys="GameCheckin.last_updated_by_user_id",
        lazy=True,
    )
    team_assignments = db.relationship(
        "GameTeamAssignment",
        back_populates="user",
        lazy=True,
    )

    @property
    def is_active(self):
        return self.account_status == AccountStatus.APPROVED

    @property
    def is_rejected(self):
        return self.account_status == AccountStatus.REJECTED

    def __repr__(self):
        return f"<User {self.email}>"
