import uuid
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app import db
from .users import PlayerPosition, UserRole

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")
CHECKIN_OPEN_HOUR = 9
CHECKIN_CLOSE_HOUR = 17
IN_PROGRESS_START_HOUR = 18
IN_PROGRESS_START_MINUTE = 30
SESSION_FINISH_HOUR = 22
DEFAULT_MAX_CONFIRMED_PLAYERS = 30


class GameSessionStatus(Enum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class CheckinStatus(Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    WAITLIST = "waitlist"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    ATTENDED = "attended"


class CheckinUpdateSource(Enum):
    SELF_SERVICE = "self_service"
    ADMIN_PANEL = "admin_panel"
    TEAM_DRAW = "team_draw"
    SYSTEM = "system"


class TeamCode(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class GameTeamAssignmentSource(Enum):
    AUTO = "auto"
    MANUAL = "manual"


class GameSession(db.Model):
    __tablename__ = "game_sessions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    game_date = db.Column(db.Date, nullable=False, unique=True)

    status = db.Column(
        db.Enum(GameSessionStatus, name="game_session_status_enum"),
        nullable=False,
        default=GameSessionStatus.SCHEDULED,
        server_default=GameSessionStatus.SCHEDULED.name,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    checkins = db.relationship(
        "GameCheckin",
        back_populates="game_session",
        cascade="all, delete-orphan",
        lazy=True,
    )
    team_assignments = db.relationship(
        "GameTeamAssignment",
        back_populates="game_session",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def weekday(self):
        return self.game_date.weekday()

    @property
    def max_players(self):
        return DEFAULT_MAX_CONFIRMED_PLAYERS

    @property
    def checkin_opens_at(self):
        if self.weekday == 0:
            open_date = self.game_date - timedelta(days=1)
        elif self.weekday == 2:
            open_date = self.game_date - timedelta(days=1)
        else:
            open_date = self.game_date

        return datetime.combine(
            open_date,
            time(hour=CHECKIN_OPEN_HOUR),
            tzinfo=BRAZIL_TZ,
        )

    @property
    def checkin_closes_at(self):
        return datetime.combine(
            self.game_date,
            time(hour=CHECKIN_CLOSE_HOUR),
            tzinfo=BRAZIL_TZ,
        )

    @property
    def in_progress_starts_at(self):
        return datetime.combine(
            self.game_date,
            time(hour=IN_PROGRESS_START_HOUR, minute=IN_PROGRESS_START_MINUTE),
            tzinfo=BRAZIL_TZ,
        )

    @property
    def finished_at(self):
        return datetime.combine(
            self.game_date,
            time(hour=SESSION_FINISH_HOUR),
            tzinfo=BRAZIL_TZ,
        )

    def resolve_status(self, current_time=None):
        current_time = current_time or datetime.now(BRAZIL_TZ)

        if self.status in {GameSessionStatus.CANCELLED, GameSessionStatus.FINISHED}:
            return self.status

        if current_time < self.checkin_opens_at:
            return GameSessionStatus.SCHEDULED

        if current_time <= self.checkin_closes_at:
            return GameSessionStatus.OPEN

        if current_time < self.in_progress_starts_at:
            return GameSessionStatus.CLOSED

        if current_time < self.finished_at:
            return GameSessionStatus.IN_PROGRESS

        return GameSessionStatus.FINISHED


class GameCheckin(db.Model):
    __tablename__ = "game_checkins"
    __table_args__ = (
        db.UniqueConstraint(
            "game_session_id",
            "user_id",
            name="uq_game_checkin_session_user",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_session_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = db.Column(
        db.Enum(CheckinStatus, name="checkin_status_enum"),
        nullable=False,
        default=CheckinStatus.CONFIRMED,
        server_default=CheckinStatus.CONFIRMED.name,
    )
    checked_in_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_updated_by_user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_updated_by_role = db.Column(
        db.Enum(UserRole, name="user_role_enum", create_type=False),
        nullable=True,
    )
    last_updated_source = db.Column(
        db.Enum(CheckinUpdateSource, name="checkin_update_source_enum"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    game_session = db.relationship("GameSession", back_populates="checkins", lazy=True)
    user = db.relationship("User", back_populates="checkins", foreign_keys=[user_id], lazy=True)
    last_updated_by = db.relationship("User", foreign_keys=[last_updated_by_user_id], lazy=True)


class GameTeamAssignment(db.Model):
    __tablename__ = "game_team_assignments"
    __table_args__ = (
        db.UniqueConstraint(
            "game_session_id",
            "user_id",
            name="uq_game_team_assignment_session_user",
        ),
        db.CheckConstraint(
            "user_id IS NOT NULL OR manual_player_name IS NOT NULL",
            name="ck_game_team_assignment_player_reference",
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_session_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_code = db.Column(
        db.Enum(TeamCode, name="team_code_enum"),
        nullable=False,
    )
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    manual_player_name = db.Column(db.String(120), nullable=True)
    manual_player_position = db.Column(
        db.Enum(PlayerPosition, name="player_position_enum", create_type=False),
        nullable=True,
    )
    source_type = db.Column(
        db.Enum(GameTeamAssignmentSource, name="game_team_assignment_source_enum"),
        nullable=False,
        default=GameTeamAssignmentSource.AUTO,
        server_default=GameTeamAssignmentSource.AUTO.name,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    game_session = db.relationship("GameSession", back_populates="team_assignments", lazy=True)
    user = db.relationship("User", back_populates="team_assignments", lazy=True)

    @property
    def display_name(self):
        if self.user:
            return self.user.name
        return self.manual_player_name or "Jogadora não informada"
