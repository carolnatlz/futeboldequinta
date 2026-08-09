import uuid
from enum import Enum

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app import db


class PinnieSize(Enum):
    PP = "PP"
    P = "P"
    M = "M"
    G = "G"
    GG = "GG"
    XGG = "XGG"


class Pinnie(db.Model):
    __tablename__ = "pinnies"
    __table_args__ = (
        db.CheckConstraint(
            "pinnie_batch_number IS NULL OR pinnie_batch_number > 0",
            name="ck_pinnies_batch_number_positive",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    pinnie_name = db.Column(db.String(120), nullable=True)
    pinnie_number = db.Column(db.Integer, unique=True, nullable=False)
    pinnie_size = db.Column(
        db.Enum(PinnieSize, name="pinnie_size_enum"),
        nullable=True,
    )
    pinnie_batch_number = db.Column(db.Integer, nullable=True)
    payment_declared = db.Column(db.Boolean, nullable=True)
    purchase_submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    deposit_paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    payment_completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    pinnie_delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="pinnie", lazy=True)

    def __repr__(self):
        return f"<Pinnie {self.pinnie_number}>"


class PinnieSettings(db.Model):
    __tablename__ = "pinnie_settings"
    __table_args__ = (
        db.CheckConstraint("id = 1", name="ck_pinnie_settings_singleton"),
        db.CheckConstraint(
            "current_batch_number > 0",
            name="ck_pinnie_settings_current_batch_positive",
        ),
    )

    id = db.Column(
        db.SmallInteger,
        primary_key=True,
        default=1,
        autoincrement=False,
    )
    current_batch_number = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
