import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


class Pinnie(db.Model):
    __tablename__ = "pinnies"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    pinnie_name = db.Column(db.String(120), nullable=True)
    pinnie_number = db.Column(db.Integer, unique=True, nullable=False)
    payment_declared = db.Column(db.Boolean, nullable=True)
    purchase_submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="pinnie", lazy=True)

    def __repr__(self):
        return f"<Pinnie {self.pinnie_number}>"
