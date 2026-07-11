import random
from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

from app import db
from app.models import (
    AccountStatus,
    CheckinUpdateSource,
    CheckinStatus,
    GameCheckin,
    GameSession,
    GameSessionStatus,
    GameTeamAssignment,
    GameTeamAssignmentSource,
    PlayerPosition,
    TeamCode,
    User,
    UserRole,
)
from app.models.game_sessions import BRAZIL_TZ

from . import main, now_utc, profile_photo_url, roles_required


CHECKIN_STATUS_ORDER = case(
    (GameCheckin.status == CheckinStatus.RESERVED, 0),
    (GameCheckin.status == CheckinStatus.CONFIRMED, 0),
    (GameCheckin.status == CheckinStatus.WAITLIST, 1),
    (GameCheckin.status == CheckinStatus.ATTENDED, 2),
    (GameCheckin.status == CheckinStatus.NO_SHOW, 3),
    (GameCheckin.status == CheckinStatus.CANCELLED, 4),
    else_=5,
)

OCCUPIED_CHECKIN_STATUSES = (
    CheckinStatus.RESERVED,
    CheckinStatus.CONFIRMED,
)

AUTO_RESERVED_ROLES = (
    UserRole.ADMIN,
    UserRole.ORGANIZER,
)

CHECKIN_STATUS_LABELS = {
    CheckinStatus.RESERVED: "Reservada",
    CheckinStatus.CONFIRMED: "Confirmada",
    CheckinStatus.WAITLIST: "Lista de espera",
    CheckinStatus.CANCELLED: "Cancelada",
    CheckinStatus.NO_SHOW: "Não compareceu",
    CheckinStatus.ATTENDED: "Presente",
}

CHECKIN_ADMIN_GROUP_ORDER = (
    CheckinStatus.RESERVED,
    CheckinStatus.CONFIRMED,
    CheckinStatus.ATTENDED,
    CheckinStatus.WAITLIST,
    CheckinStatus.CANCELLED,
    CheckinStatus.NO_SHOW,
)

CHECKIN_UPDATE_SOURCE_LABELS = {
    CheckinUpdateSource.SELF_SERVICE: "Autoatendimento",
    CheckinUpdateSource.ADMIN_PANEL: "Painel admin",
    CheckinUpdateSource.TEAM_DRAW: "Sorteio dos times",
    CheckinUpdateSource.SYSTEM: "Sistema",
}

SESSION_STATUS_LABELS = {
    GameSessionStatus.SCHEDULED: "Agendado",
    GameSessionStatus.OPEN: "Check-in aberto",
    GameSessionStatus.CLOSED: "Check-in encerrado",
    GameSessionStatus.IN_PROGRESS: "Em andamento",
    GameSessionStatus.FINISHED: "Finalizado",
    GameSessionStatus.CANCELLED: "Cancelado",
}

WEEKDAY_LABELS = {
    0: "Segunda-Feira",
    1: "Terça-Feira",
    2: "Quarta-Feira",
    3: "Quinta-Feira",
    4: "Sexta-Feira",
    5: "Sábado",
    6: "Domingo",
}

POSITION_LABELS = {
    "gol": "Goleira",
    "ataque": "Ataque",
    "defesa": "Defesa",
}

CONFIRMED_PREVIEW_LIMIT = 5
WAITLIST_PREVIEW_LIMIT = 3
TEAM_CODES = (
    TeamCode.A,
    TeamCode.B,
    TeamCode.C,
    TeamCode.D,
    TeamCode.E,
    TeamCode.F,
)
TEAM_DRAW_ALLOWED_STATUSES = (
    GameSessionStatus.CLOSED,
    GameSessionStatus.IN_PROGRESS,
    GameSessionStatus.FINISHED,
)
TEAM_DRAW_ATTENDANCE_ALLOWED_STATUSES = (
    GameSessionStatus.IN_PROGRESS,
    GameSessionStatus.FINISHED,
)

#TEMP
def _local_now():
    return datetime.now(BRAZIL_TZ)

#DEBUG ONLY: used to simulate time-based behavior during development, should be commented for production
# def _local_now():
#     return datetime(2026, 6, 1, 18, 40, tzinfo=BRAZIL_TZ)


def _sync_sessions_and_organizers(sessions):
    sessions = list(sessions)
    if not sessions:
        return

    current_time = _local_now()
    changed = False
    auto_reserved_users = (
        User.query.filter(
            User.role.in_(AUTO_RESERVED_ROLES),
            User.account_status == AccountStatus.APPROVED,
        )
        .order_by(User.created_at.asc())
        .all()
    )
    eligible_user_ids = {user.id for user in auto_reserved_users}

    for session in sessions:
        resolved_status = session.resolve_status(current_time)
        if session.status != resolved_status:
            session.status = resolved_status
            changed = True

        if session.status in {GameSessionStatus.CANCELLED, GameSessionStatus.FINISHED}:
            continue

        reserved_checkins = GameCheckin.query.filter(
            GameCheckin.game_session_id == session.id,
            GameCheckin.status == CheckinStatus.RESERVED,
        ).all()

        for reserved_checkin in reserved_checkins:
            if reserved_checkin.user_id in eligible_user_ids:
                continue

            reserved_checkin.status = CheckinStatus.CANCELLED
            reserved_checkin.cancelled_at = now_utc()
            _stamp_checkin_audit(reserved_checkin)
            if _should_promote_waitlist(session):
                _promote_waitlist(session.id)
            changed = True

        auto_reserved_checkins = (
            {
                checkin.user_id: checkin
                for checkin in GameCheckin.query.filter(
                    GameCheckin.game_session_id == session.id,
                    GameCheckin.user_id.in_(eligible_user_ids),
                ).all()
            }
            if eligible_user_ids
            else {}
        )

        for user in auto_reserved_users:
            existing_checkin = auto_reserved_checkins.get(user.id)
            if not existing_checkin:
                db.session.add(
                    _build_checkin(
                        game_session=session,
                        user=user,
                        status=CheckinStatus.RESERVED,
                        source=CheckinUpdateSource.SYSTEM,
                    )
                )
                changed = True

    if changed:
        db.session.commit()


def _can_user_checkin(session, user, checkin=None):
    if session.status != GameSessionStatus.OPEN:
        return False

    if user.role in AUTO_RESERVED_ROLES:
        return bool(checkin and checkin.status == CheckinStatus.CANCELLED)

    return not checkin or checkin.status == CheckinStatus.CANCELLED


def _can_user_cancel(session, checkin):
    return (
        checkin.status in {CheckinStatus.RESERVED, CheckinStatus.CONFIRMED, CheckinStatus.WAITLIST}
        and session.status == GameSessionStatus.OPEN
    )


def _occupied_count(session_id):
    return (
        db.session.query(func.count(GameCheckin.id))
        .filter(
            GameCheckin.game_session_id == session_id,
            GameCheckin.status.in_(OCCUPIED_CHECKIN_STATUSES),
        )
        .scalar()
        or 0
    )


def _should_promote_waitlist(session):
    return session.status in {GameSessionStatus.SCHEDULED, GameSessionStatus.OPEN}


def _promote_waitlist(session_id):
    waitlisted = (
        GameCheckin.query.filter_by(
            game_session_id=session_id,
            status=CheckinStatus.WAITLIST,
        )
        .order_by(GameCheckin.checked_in_at.asc(), GameCheckin.created_at.asc())
        .first()
    )
    if not waitlisted:
        return None

    waitlisted.status = CheckinStatus.CONFIRMED
    waitlisted.cancelled_at = None
    _stamp_checkin_audit(waitlisted)
    return waitlisted


def _stamp_checkin_audit(checkin, acting_user=None, source=CheckinUpdateSource.SYSTEM):
    checkin.last_updated_source = source
    if acting_user:
        checkin.last_updated_by = acting_user
        checkin.last_updated_by_role = acting_user.role
    else:
        checkin.last_updated_by = None
        checkin.last_updated_by_role = None
    return checkin


def _build_checkin(*, game_session, user, status, source, acting_user=None):
    checkin = GameCheckin(
        game_session=game_session,
        user=user,
        status=status,
    )
    return _stamp_checkin_audit(checkin, acting_user=acting_user, source=source)


def _session_status_badge(status):
    if status == GameSessionStatus.OPEN:
        return "checkin-badge-open"
    if status == GameSessionStatus.CLOSED:
        return "checkin-badge-closed"
    if status == GameSessionStatus.IN_PROGRESS:
        return "checkin-badge-in-progress"
    if status == GameSessionStatus.CANCELLED:
        return "checkin-badge-cancelled"
    if status == GameSessionStatus.FINISHED:
        return "checkin-badge-finished"
    return "checkin-badge-scheduled"


def _checkin_status_badge(status):
    if status == CheckinStatus.RESERVED:
        return "checkin-badge-confirmed"
    if status == CheckinStatus.CONFIRMED:
        return "checkin-badge-confirmed"
    if status == CheckinStatus.WAITLIST:
        return "checkin-badge-waitlist"
    if status == CheckinStatus.CANCELLED:
        return "checkin-badge-cancelled"
    if status == CheckinStatus.ATTENDED:
        return "checkin-badge-attended"
    return "checkin-badge-no-show"


def _format_time_label(dt):
    if dt.minute:
        return dt.strftime("%-Hh%M")
    return dt.strftime("%-Hh")


def _format_brt_datetime(dt):
    if not dt:
        return "—"
    return f"{dt.astimezone(BRAZIL_TZ).strftime('%d/%m/%Y %H:%M')} BRT"


def _group_checkins_by_status(checkins):
    grouped_checkins = {status: [] for status in CHECKIN_ADMIN_GROUP_ORDER}
    for checkin in checkins:
        grouped_checkins.setdefault(checkin.status, []).append(checkin)

    return [
        {
            "status": status,
            "label": CHECKIN_STATUS_LABELS[status],
            "checkins": grouped_checkins.get(status, []),
        }
        for status in CHECKIN_ADMIN_GROUP_ORDER
    ]


def _session_window_label(session):
    if session.status == GameSessionStatus.SCHEDULED:
        return f"Check-in abre às {_format_time_label(session.checkin_opens_at)}"
    if session.status == GameSessionStatus.OPEN:
        return f"Check-in aberto até {_format_time_label(session.checkin_closes_at)}"
    if session.status == GameSessionStatus.CLOSED:
        return f"Jogo começa às {_format_time_label(session.in_progress_starts_at)}"
    if session.status == GameSessionStatus.IN_PROGRESS:
        return f"Jogo até {_format_time_label(session.finished_at)}"
    if session.status == GameSessionStatus.CANCELLED:
        return "Sessão cancelada"
    return "Sessão finalizada"


def _position_label(user):
    return _position_label_from_position(user.position if user else None)


def _position_label_from_position(position):
    if not position:
        return "Sem posição"
    position_value = position.value if hasattr(position, "value") else str(position).lower()
    return POSITION_LABELS.get(position_value, position_value.capitalize())


def _serialize_signup_row(checkin, index, kind):
    is_current_user = checkin.user_id == current_user.id
    return {
        "checkin": checkin,
        "index": index,
        "kind": kind,
        "is_current_user": is_current_user,
        "name": checkin.user.name,
        "position": _position_label(checkin.user),
        "status_label": CHECKIN_STATUS_LABELS.get(checkin.status, "Confirmada"),
        "status_badge": _checkin_status_badge(checkin.status),
        "profile_img_url": profile_photo_url(checkin.user.profile_img),
    }


def _serialize_session(
    session,
    current_user_checkins,
    confirmed_counts,
    waitlist_counts,
    waitlist_positions,
):
    user_checkin = current_user_checkins.get(session.id)
    can_checkin = _can_user_checkin(session, current_user, user_checkin)
    return {
        "session": session,
        "user_checkin": user_checkin,
        "confirmed_count": confirmed_counts.get(session.id, 0),
        "waitlist_count": waitlist_counts.get(session.id, 0),
        "status_label": SESSION_STATUS_LABELS[session.status],
        "status_badge": _session_status_badge(session.status),
        "checkin_status_label": CHECKIN_STATUS_LABELS.get(user_checkin.status) if user_checkin else None,
        "checkin_status_badge": _checkin_status_badge(user_checkin.status) if user_checkin else None,
        "can_checkin": can_checkin,
        "can_cancel": bool(user_checkin and _can_user_cancel(session, user_checkin)),
        "checkin_action_label": "Confirmada",
        "exit_action_label": "Sair",
        "waitlist_position": waitlist_positions.get(session.id),
        "display_date": f"{WEEKDAY_LABELS[session.game_date.weekday()]}, {session.game_date.strftime('%d/%m/%Y')}",
        "window_label": _session_window_label(session),
    }


def _can_draw_teams(session):
    return session.status in TEAM_DRAW_ALLOWED_STATUSES


def _build_admin_session_cards(limit=2):
    today = _local_now().date()
    sessions = (
        GameSession.query.filter(GameSession.game_date >= today)
        .order_by(GameSession.game_date.asc())
        .limit(limit)
        .all()
    )
    _sync_sessions_and_organizers(sessions)
    sessions = (
        GameSession.query.filter(GameSession.game_date >= today)
        .order_by(GameSession.game_date.asc())
        .limit(limit)
        .all()
    )

    session_ids = [session.id for session in sessions]
    confirmed_counts = {}
    waitlist_counts = {}
    assignment_counts = {}

    if session_ids:
        confirmed_counts = {
            session_id: count
            for session_id, count in db.session.query(
                GameCheckin.game_session_id,
                func.count(GameCheckin.id),
            )
            .filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.status.in_(OCCUPIED_CHECKIN_STATUSES),
            )
            .group_by(GameCheckin.game_session_id)
            .all()
        }
        waitlist_counts = {
            session_id: count
            for session_id, count in db.session.query(
                GameCheckin.game_session_id,
                func.count(GameCheckin.id),
            )
            .filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.status == CheckinStatus.WAITLIST,
            )
            .group_by(GameCheckin.game_session_id)
            .all()
        }
        assignment_counts = {
            session_id: count
            for session_id, count in db.session.query(
                GameTeamAssignment.game_session_id,
                func.count(GameTeamAssignment.id),
            )
            .filter(GameTeamAssignment.game_session_id.in_(session_ids))
            .group_by(GameTeamAssignment.game_session_id)
            .all()
        }

    return [
        {
            "session": session,
            "confirmed_count": confirmed_counts.get(session.id, 0),
            "waitlist_count": waitlist_counts.get(session.id, 0),
            "assignment_count": assignment_counts.get(session.id, 0),
            "teams_drawn": assignment_counts.get(session.id, 0) > 0,
            "can_draw_teams": _can_draw_teams(session),
            "status_label": SESSION_STATUS_LABELS[session.status],
            "status_badge": _session_status_badge(session.status),
            "display_date": f"{WEEKDAY_LABELS[session.game_date.weekday()]}, {session.game_date.strftime('%d/%m/%Y')}",
            "weekday_label": WEEKDAY_LABELS[session.game_date.weekday()],
            "date_label": session.game_date.strftime('%d/%m/%Y'),
        }
        for session in sessions
    ]


def _confirmed_checkins_for_team_draw(session_id):
    return (
        GameCheckin.query.filter(
            GameCheckin.game_session_id == session_id,
            GameCheckin.status.in_(OCCUPIED_CHECKIN_STATUSES),
        )
        .join(User, User.id == GameCheckin.user_id)
        .order_by(GameCheckin.checked_in_at.asc(), User.name.asc())
        .all()
    )


def _display_checkins_for_team_draw(session_id):
    return (
        GameCheckin.query.filter(
            GameCheckin.game_session_id == session_id,
            GameCheckin.status.in_(
                (
                    CheckinStatus.RESERVED,
                    CheckinStatus.CONFIRMED,
                    CheckinStatus.ATTENDED,
                )
            ),
        )
        .join(User, User.id == GameCheckin.user_id)
        .order_by(GameCheckin.checked_in_at.asc(), User.name.asc())
        .all()
    )


def _build_auto_team_assignments(session, confirmed_checkins):
    rng = random.SystemRandom()
    grouped_checkins = {
        PlayerPosition.GOL: [],
        PlayerPosition.DEFESA: [],
        PlayerPosition.ATAQUE: [],
        None: [],
    }

    for checkin in confirmed_checkins:
        grouped_checkins.setdefault(checkin.user.position, [])
        grouped_checkins[checkin.user.position].append(checkin)

    for group in grouped_checkins.values():
        rng.shuffle(group)

    assignments = []
    team_index = 0

    for position_key in (
        PlayerPosition.GOL,
        PlayerPosition.DEFESA,
        PlayerPosition.ATAQUE,
        None,
    ):
        for checkin in grouped_checkins.get(position_key, []):
            assignments.append(
                GameTeamAssignment(
                    game_session=session,
                    team_code=TEAM_CODES[team_index % len(TEAM_CODES)],
                    user=checkin.user,
                    source_type=GameTeamAssignmentSource.AUTO,
                )
            )
            team_index += 1

    return assignments


def _serialize_team_assignment(assignment, checkin_status_by_user_id=None):
    checkin_status_by_user_id = checkin_status_by_user_id or {}
    return {
        "assignment": assignment,
        "is_manual": assignment.source_type == GameTeamAssignmentSource.MANUAL,
        "name": assignment.display_name,
        "position_label": (
            _position_label(assignment.user)
            if assignment.user
            else _position_label_from_position(assignment.manual_player_position)
        ),
        "position_key": (
            assignment.user.position.name
            if assignment.user and assignment.user.position
            else assignment.manual_player_position.name
            if assignment.manual_player_position
            else "NONE"
        ),
        "profile_img_url": (
            profile_photo_url(assignment.user.profile_img)
            if assignment.user
            else profile_photo_url(None)
        ),
        "checkin_status_value": (
            checkin_status_by_user_id.get(assignment.user_id).name.lower()
            if assignment.user_id and checkin_status_by_user_id.get(assignment.user_id)
            else None
        ),
    }


def _team_buckets(assignments, checkin_status_by_user_id=None):
    grouped_assignments = {team_code: [] for team_code in TEAM_CODES}

    for assignment in assignments:
        grouped_assignments.setdefault(assignment.team_code, [])
        grouped_assignments[assignment.team_code].append(
            _serialize_team_assignment(assignment, checkin_status_by_user_id)
        )

    return [
        {
            "code": team_code.value,
            "label": f"Time {team_code.value}",
            "players": grouped_assignments.get(team_code, []),
            "player_count": len(grouped_assignments.get(team_code, [])),
            "placeholder_slots": max(0, 5 - len(grouped_assignments.get(team_code, []))),
        }
        for team_code in TEAM_CODES
    ]


def _build_team_draw_position_cards(confirmed_checkins, total_slots):
    position_counts = [
        {
            "label": "Goleiras",
            "count": sum(1 for checkin in confirmed_checkins if checkin.user.position == PlayerPosition.GOL),
            "icon_emoji": "🧤",
            "accent_class": "team-draw-position-card-goalkeepers",
        },
        {
            "label": "Defesas",
            "count": sum(1 for checkin in confirmed_checkins if checkin.user.position == PlayerPosition.DEFESA),
            "icon_emoji": "🛡️",
            "accent_class": "team-draw-position-card-defenders",
        },
        {
            "label": "Ataques",
            "count": sum(1 for checkin in confirmed_checkins if checkin.user.position == PlayerPosition.ATAQUE),
            "icon_emoji": "👟",
            "accent_class": "team-draw-position-card-attackers",
        },
        {
            "label": "Sem posição",
            "count": sum(1 for checkin in confirmed_checkins if not checkin.user.position),
            "icon_emoji": "👕",
            "accent_class": "team-draw-position-card-unassigned",
        },
    ]

    for item in position_counts:
        if total_slots > 0:
            bar_width = round((item["count"] / total_slots) * 100)
        else:
            bar_width = 0
        item["bar_width"] = bar_width

    return position_counts


def _first_available_team_draw_session():
    today = _local_now().date()
    sessions = (
        GameSession.query.filter(GameSession.game_date >= today)
        .order_by(GameSession.game_date.asc())
        .all()
    )
    _sync_sessions_and_organizers(sessions)

    for session in sessions:
        if _can_draw_teams(session) and session.status != GameSessionStatus.CANCELLED:
            return session

    return None


@main.route("/check-ins/<uuid:session_id>/inscricoes")
@login_required
def lista_checkins_sessao(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    active_checkins = (
        GameCheckin.query.filter(
            GameCheckin.game_session_id == session.id,
            GameCheckin.status.in_(
                (
                    CheckinStatus.RESERVED,
                    CheckinStatus.CONFIRMED,
                    CheckinStatus.WAITLIST,
                )
            ),
        )
        .join(User, User.id == GameCheckin.user_id)
        .order_by(CHECKIN_STATUS_ORDER, GameCheckin.checked_in_at.asc(), User.name.asc())
        .all()
    )

    confirmed_checkins = [
        checkin for checkin in active_checkins if checkin.status in OCCUPIED_CHECKIN_STATUSES
    ]
    waitlist_checkins = [
        checkin for checkin in active_checkins if checkin.status == CheckinStatus.WAITLIST
    ]

    confirmed_rows = [
        _serialize_signup_row(checkin, index, "confirmed")
        for index, checkin in enumerate(confirmed_checkins, start=1)
    ]
    waitlist_rows = [
        _serialize_signup_row(checkin, index, "waitlist")
        for index, checkin in enumerate(waitlist_checkins, start=1)
    ]

    return render_template(
        "checkins/lista_inscricoes.html",
        session=session,
        status_label=SESSION_STATUS_LABELS[session.status],
        status_badge=_session_status_badge(session.status),
        confirmed_count=len(confirmed_checkins),
        waitlist_count=len(waitlist_checkins),
        total_signups=len(confirmed_checkins) + len(waitlist_checkins),
        available_spots=max(session.max_players - len(confirmed_checkins), 0),
        confirmed_rows=confirmed_rows,
        waitlist_rows=waitlist_rows,
        confirmed_preview_limit=CONFIRMED_PREVIEW_LIMIT,
        waitlist_preview_limit=WAITLIST_PREVIEW_LIMIT,
        display_date=f"{WEEKDAY_LABELS[session.game_date.weekday()]}, {session.game_date.strftime('%d/%m/%Y')}",
    )


@main.route("/check-ins")
@login_required
def inscricoes_nos_jogos():
    today = _local_now().date()
    sessions = (
        GameSession.query.filter(GameSession.game_date >= today)
        .order_by(GameSession.game_date.asc())
        .limit(2)
        .all()
    )
    _sync_sessions_and_organizers(sessions)
    sessions = (
        GameSession.query.filter(GameSession.game_date >= today)
        .order_by(GameSession.game_date.asc())
        .limit(2)
        .all()
    )

    session_ids = [session.id for session in sessions]
    current_user_checkins = {}
    confirmed_counts = {}
    waitlist_counts = {}
    waitlist_positions = {}

    if session_ids:
        current_user_checkins = {
            checkin.game_session_id: checkin
            for checkin in GameCheckin.query.filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.user_id == current_user.id,
            ).all()
        }
        confirmed_counts = {
            session_id: count
            for session_id, count in db.session.query(
                GameCheckin.game_session_id,
                func.count(GameCheckin.id),
            )
            .filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.status.in_(OCCUPIED_CHECKIN_STATUSES),
            )
            .group_by(GameCheckin.game_session_id)
            .all()
        }
        waitlist_counts = {
            session_id: count
            for session_id, count in db.session.query(
                GameCheckin.game_session_id,
                func.count(GameCheckin.id),
            )
            .filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.status == CheckinStatus.WAITLIST,
            )
            .group_by(GameCheckin.game_session_id)
            .all()
        }
        waitlist_position_rows = (
            db.session.query(
                GameCheckin.game_session_id,
                GameCheckin.user_id,
                func.row_number()
                .over(
                    partition_by=GameCheckin.game_session_id,
                    order_by=(GameCheckin.checked_in_at.asc(), User.name.asc()),
                )
                .label("position"),
            )
            .join(User, User.id == GameCheckin.user_id)
            .filter(
                GameCheckin.game_session_id.in_(session_ids),
                GameCheckin.status == CheckinStatus.WAITLIST,
            )
            .all()
        )
        waitlist_positions = {
            session_id: position
            for session_id, user_id, position in waitlist_position_rows
            if user_id == current_user.id
        }

    session_cards = [
        _serialize_session(
            session,
            current_user_checkins,
            confirmed_counts,
            waitlist_counts,
            waitlist_positions,
        )
        for session in sessions
    ]

    return render_template("checkins/inscricoes_nos_jogos.html", session_cards=session_cards)


@main.route("/check-ins/<uuid:session_id>/entrar", methods=["POST"])
@login_required
def entrar_checkin(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    existing_checkin = GameCheckin.query.filter_by(
        game_session_id=session.id,
        user_id=current_user.id,
    ).first()

    if not _can_user_checkin(session, current_user, existing_checkin):
        if (
            current_user.role in AUTO_RESERVED_ROLES
            and existing_checkin
            and existing_checkin.status == CheckinStatus.CANCELLED
        ):
            flash("Seu check-in foi cancelado. Clique em Confirmada para voltar para a sessão.", "alert-info")
        elif current_user.role in AUTO_RESERVED_ROLES and existing_checkin:
            flash("Sua vaga garantida já está reservada para esta sessão.", "alert-info")
        else:
            flash("O check-in dessa sessão não está aberto no momento.", "alert-warning")
        return redirect(url_for("main.inscricoes_nos_jogos"))

    if existing_checkin and existing_checkin.status != CheckinStatus.CANCELLED:
        flash("Você já possui check-in ativo para essa sessão.", "alert-info")
        return redirect(url_for("main.inscricoes_nos_jogos"))

    new_status = (
        CheckinStatus.CONFIRMED
        if _occupied_count(session.id) < session.max_players
        else CheckinStatus.WAITLIST
    )

    if existing_checkin:
        existing_checkin.status = new_status
        existing_checkin.checked_in_at = now_utc()
        existing_checkin.cancelled_at = None
        _stamp_checkin_audit(
            existing_checkin,
            acting_user=current_user,
            source=CheckinUpdateSource.SELF_SERVICE,
        )
    else:
        db.session.add(
            _build_checkin(
                game_session=session,
                user=current_user,
                status=new_status,
                source=CheckinUpdateSource.SELF_SERVICE,
                acting_user=current_user,
            )
        )

    db.session.commit()

    if new_status == CheckinStatus.CONFIRMED:
        flash("Seu check-in foi confirmado com sucesso.", "alert-success")
    else:
        flash("As vagas confirmadas esgotaram. Você entrou na lista de espera.", "alert-warning")

    return redirect(url_for("main.inscricoes_nos_jogos"))


@main.route("/check-ins/<uuid:session_id>/cancelar", methods=["POST"])
@login_required
def cancelar_checkin(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    checkin = GameCheckin.query.filter_by(
        game_session_id=session.id,
        user_id=current_user.id,
    ).first_or_404()

    if not _can_user_cancel(session, checkin):
        flash("Esse check-in não pode mais ser cancelado.", "alert-warning")
        return redirect(url_for("main.inscricoes_nos_jogos"))

    was_occupying_slot = checkin.status in OCCUPIED_CHECKIN_STATUSES
    checkin.status = CheckinStatus.CANCELLED
    checkin.cancelled_at = now_utc()
    _stamp_checkin_audit(
        checkin,
        acting_user=current_user,
        source=CheckinUpdateSource.SELF_SERVICE,
    )

    promoted = (
        _promote_waitlist(session.id)
        if was_occupying_slot and _should_promote_waitlist(session)
        else None
    )
    db.session.commit()

    if promoted:
        flash("Check-in cancelado e a primeira pessoa da fila foi promovida automaticamente.", "alert-info")
    elif was_occupying_slot and session.status in {
        GameSessionStatus.CLOSED,
        GameSessionStatus.IN_PROGRESS,
        GameSessionStatus.FINISHED,
    }:
        flash(
            "Check-in cancelado com sucesso. A fila de espera foi congelada para esta sessão.",
            "alert-info",
        )
    else:
        flash("Check-in cancelado com sucesso.", "alert-success")

    return redirect(url_for("main.inscricoes_nos_jogos"))


@main.route("/admin/check-ins")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_checkins():
    return render_template(
        "admin/gestao_dos_jogos.html",
        session_cards=_build_admin_session_cards(limit=2),
    )


@main.route("/admin/sorteio-times")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_team_draws():
    session = _first_available_team_draw_session()
    if session:
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    return render_template("admin/sorteio_times_indisponivel.html")


@main.route("/admin/sorteio-times/<uuid:session_id>")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_team_draw_session(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    display_checkins = _display_checkins_for_team_draw(session.id)
    checkin_status_by_user_id = {
        checkin.user_id: checkin.status
        for checkin in display_checkins
    }
    waitlist_count = (
        db.session.query(func.count(GameCheckin.id))
        .filter(
            GameCheckin.game_session_id == session.id,
            GameCheckin.status == CheckinStatus.WAITLIST,
        )
        .scalar()
        or 0
    )
    assignments = (
        GameTeamAssignment.query.filter_by(game_session_id=session.id)
        .order_by(GameTeamAssignment.created_at.asc())
        .all()
    )

    return render_template(
        "admin/sorteio_times.html",
        session=session,
        display_date=f"{WEEKDAY_LABELS[session.game_date.weekday()]}, {session.game_date.strftime('%d/%m/%Y')}",
        weekday_label=WEEKDAY_LABELS[session.game_date.weekday()],
        date_label=session.game_date.strftime('%d/%m/%Y'),
        status_label=SESSION_STATUS_LABELS[session.status],
        status_badge=_session_status_badge(session.status),
        confirmed_count=len(display_checkins),
        waitlist_count=waitlist_count,
        assignment_count=len(assignments),
        teams_drawn=bool(assignments),
        can_draw_teams=_can_draw_teams(session),
        attendance_controls_enabled=session.status in TEAM_DRAW_ATTENDANCE_ALLOWED_STATUSES,
        position_cards=_build_team_draw_position_cards(display_checkins, session.max_players),
        team_buckets=_team_buckets(assignments, checkin_status_by_user_id),
    )


@main.route("/admin/sorteio-times/<uuid:session_id>/gerar", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_generate_team_draw(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    if not _can_draw_teams(session):
        flash("O sorteio dos times fica disponível após o encerramento do check-in.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    confirmed_checkins = _confirmed_checkins_for_team_draw(session.id)
    if not confirmed_checkins:
        flash("Ainda não existem jogadoras confirmadas para gerar os times dessa sessão.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    GameTeamAssignment.query.filter_by(game_session_id=session.id).delete(synchronize_session=False)

    for assignment in _build_auto_team_assignments(session, confirmed_checkins):
        db.session.add(assignment)

    db.session.commit()

    flash("Times sorteados com sucesso para essa sessão.", "alert-success")
    return redirect(url_for("main.admin_team_draw_session", session_id=session.id))


@main.route("/admin/sorteio-times/<uuid:session_id>/times/<team_code>/manual", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_add_manual_team_player(session_id, team_code):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    if session.status == GameSessionStatus.CANCELLED:
        flash("Sessões canceladas não permitem alterações nos times.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    if not _can_draw_teams(session):
        flash("A inclusão manual de jogadoras fica disponível após o encerramento do check-in.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    try:
        team_code_enum = TeamCode[team_code]
    except KeyError:
        flash("Time inválido para inclusão manual.", "alert-danger")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    manual_player_name = (request.form.get("manual_player_name") or "").strip()
    manual_player_position_name = (request.form.get("manual_player_position") or "").strip()

    if not manual_player_name:
        flash("Informe o nome da jogadora manual.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    manual_player_position = None
    if manual_player_position_name and manual_player_position_name != "NONE":
        try:
            manual_player_position = PlayerPosition[manual_player_position_name]
        except KeyError:
            flash("Posição inválida para a jogadora manual.", "alert-danger")
            return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    current_team_count = (
        db.session.query(func.count(GameTeamAssignment.id))
        .filter(
            GameTeamAssignment.game_session_id == session.id,
            GameTeamAssignment.team_code == team_code_enum,
        )
        .scalar()
        or 0
    )

    if current_team_count >= 5:
        flash("Esse time já está completo com 5 jogadoras.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    db.session.add(
        GameTeamAssignment(
            game_session=session,
            team_code=team_code_enum,
            user=None,
            manual_player_name=manual_player_name,
            manual_player_position=manual_player_position,
            source_type=GameTeamAssignmentSource.MANUAL,
        )
    )
    db.session.commit()

    flash("Jogadora manual adicionada ao time com sucesso.", "alert-success")
    return redirect(url_for("main.admin_team_draw_session", session_id=session.id))


@main.route("/admin/sorteio-times/<uuid:session_id>/times/manual/<uuid:assignment_id>", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_update_manual_team_player(session_id, assignment_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    if session.status == GameSessionStatus.CANCELLED:
        flash("Sessões canceladas não permitem alterações nos times.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    if not _can_draw_teams(session):
        flash("A edição manual de jogadoras fica disponível após o encerramento do check-in.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    assignment = GameTeamAssignment.query.get_or_404(assignment_id)
    if assignment.game_session_id != session.id:
        flash("Jogadora manual inválida para esta sessão.", "alert-danger")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    if assignment.source_type != GameTeamAssignmentSource.MANUAL:
        flash("Apenas jogadoras manuais podem ser editadas por este fluxo.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    manual_player_name = (request.form.get("manual_player_name") or "").strip()
    manual_player_position_name = (request.form.get("manual_player_position") or "").strip()

    if not manual_player_name:
        flash("Informe o nome da jogadora manual.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    manual_player_position = None
    if manual_player_position_name and manual_player_position_name != "NONE":
        try:
            manual_player_position = PlayerPosition[manual_player_position_name]
        except KeyError:
            flash("Posição inválida para a jogadora manual.", "alert-danger")
            return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    assignment.manual_player_name = manual_player_name
    assignment.manual_player_position = manual_player_position
    db.session.commit()

    flash("Jogadora manual atualizada com sucesso.", "alert-success")
    return redirect(url_for("main.admin_team_draw_session", session_id=session.id))


@main.route("/admin/sorteio-times/<uuid:session_id>/presenca/<uuid:assignment_id>/<status_name>", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_update_team_draw_attendance(session_id, assignment_id, status_name):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    if session.status == GameSessionStatus.CANCELLED:
        flash("Sessões canceladas não permitem alterações nos times.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    if session.status not in TEAM_DRAW_ATTENDANCE_ALLOWED_STATUSES:
        flash("A marcação de presença fica disponível quando a sessão estiver em andamento ou finalizada.", "alert-warning")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    assignment = GameTeamAssignment.query.get_or_404(assignment_id)
    if assignment.game_session_id != session.id:
        flash("Jogadora inválida para esta sessão.", "alert-danger")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    try:
        new_status = CheckinStatus[status_name]
    except KeyError:
        flash("Status inválido para a jogadora.", "alert-danger")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    if new_status not in {CheckinStatus.ATTENDED, CheckinStatus.NO_SHOW}:
        flash("A tela de sorteio só permite marcar Presente ou Faltou.", "alert-danger")
        return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

    player_name = assignment.display_name

    if assignment.user_id:
        checkin = GameCheckin.query.filter_by(
            game_session_id=session.id,
            user_id=assignment.user_id,
        ).first()
        if not checkin:
            flash("Não foi possível localizar o check-in dessa jogadora.", "alert-danger")
            return redirect(url_for("main.admin_team_draw_session", session_id=session.id))

        checkin.status = new_status
        checkin.cancelled_at = None
        _stamp_checkin_audit(
            checkin,
            acting_user=current_user,
            source=CheckinUpdateSource.TEAM_DRAW,
        )

        if new_status == CheckinStatus.NO_SHOW:
            db.session.delete(assignment)
            flash(f"{player_name} foi marcada como faltou e removida do time.", "alert-warning")
        else:
            flash(f"{player_name} foi marcada como presente.", "alert-success")
    else:
        if new_status == CheckinStatus.NO_SHOW:
            db.session.delete(assignment)
            flash(f"{player_name} foi removida do time como faltou.", "alert-warning")
        else:
            flash(f"{player_name} foi mantida como presente no time.", "alert-success")

    db.session.commit()
    return redirect(url_for("main.admin_team_draw_session", session_id=session.id))


@main.route("/admin/check-ins/<uuid:session_id>/cancelar-sessao", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_cancelar_sessao(session_id):
    session = GameSession.query.get_or_404(session_id)
    session.status = GameSessionStatus.CANCELLED
    db.session.commit()

    flash("Sessão cancelada com sucesso.", "alert-success")
    return redirect(url_for("main.admin_checkins"))


@main.route("/admin/check-ins/<uuid:session_id>")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_checkins_sessao(session_id):
    session = GameSession.query.get_or_404(session_id)
    _sync_sessions_and_organizers([session])
    session = GameSession.query.get_or_404(session_id)

    checkins = (
        GameCheckin.query.filter_by(game_session_id=session.id)
        .join(User, User.id == GameCheckin.user_id)
        .order_by(CHECKIN_STATUS_ORDER, GameCheckin.checked_in_at.asc(), User.name.asc())
        .all()
    )

    confirmed_count = sum(1 for checkin in checkins if checkin.status in OCCUPIED_CHECKIN_STATUSES)
    waitlist_count = sum(1 for checkin in checkins if checkin.status == CheckinStatus.WAITLIST)

    return render_template(
        "checkins/checkin_sessao.html",
        session=session,
        checkins=checkins,
        grouped_checkins=_group_checkins_by_status(checkins),
        confirmed_count=confirmed_count,
        waitlist_count=waitlist_count,
        is_admin_view=current_user.role == UserRole.ADMIN,
        checkin_status_labels=CHECKIN_STATUS_LABELS,
        checkin_update_source_labels=CHECKIN_UPDATE_SOURCE_LABELS,
        session_status_labels=SESSION_STATUS_LABELS,
        format_brt_datetime=_format_brt_datetime,
    )


@main.route("/admin/check-ins/<uuid:checkin_id>/status/<status_name>", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_atualizar_status_checkin(checkin_id, status_name):
    checkin = GameCheckin.query.get_or_404(checkin_id)
    session = GameSession.query.get_or_404(checkin.game_session_id)
    previous_status = checkin.status

    if session.status == GameSessionStatus.CANCELLED:
        flash("Sessões canceladas não permitem alterações nos check-ins.", "alert-warning")
        return redirect(url_for("main.admin_checkins_sessao", session_id=checkin.game_session_id))

    try:
        new_status = CheckinStatus[status_name]
    except KeyError:
        flash("Status inválido para atualização.", "alert-danger")
        return redirect(url_for("main.admin_checkins_sessao", session_id=checkin.game_session_id))

    if new_status not in {
        CheckinStatus.CONFIRMED,
        CheckinStatus.CANCELLED,
    }:
        flash("Esse status não pode ser ajustado manualmente nessa tela.", "alert-danger")
        return redirect(url_for("main.admin_checkins_sessao", session_id=checkin.game_session_id))

    if new_status == CheckinStatus.CANCELLED:
        checkin.status = CheckinStatus.CANCELLED
        checkin.cancelled_at = now_utc()
        _stamp_checkin_audit(
            checkin,
            acting_user=current_user,
            source=CheckinUpdateSource.ADMIN_PANEL,
        )
        promoted = None
        if previous_status in OCCUPIED_CHECKIN_STATUSES and _should_promote_waitlist(session):
            promoted = _promote_waitlist(checkin.game_session_id)

        if promoted:
            flash("Jogadora removida da lista e a primeira da fila foi promovida automaticamente.", "alert-info")
        elif previous_status in OCCUPIED_CHECKIN_STATUSES and session.status in {
            GameSessionStatus.CLOSED,
            GameSessionStatus.IN_PROGRESS,
            GameSessionStatus.FINISHED,
        }:
            flash(
                "Jogadora removida da lista oficial. A fila de espera foi congelada para esta sessão.",
                "alert-info",
            )
        else:
            flash("Jogadora removida da lista com sucesso.", "alert-success")
    else:
        occupied_count = _occupied_count(session.id)
        if previous_status in OCCUPIED_CHECKIN_STATUSES:
            occupied_count = max(occupied_count - 1, 0)

        checkin.status = (
            CheckinStatus.CONFIRMED
            if occupied_count < session.max_players
            else CheckinStatus.WAITLIST
        )
        checkin.checked_in_at = now_utc()
        checkin.cancelled_at = None
        _stamp_checkin_audit(
            checkin,
            acting_user=current_user,
            source=CheckinUpdateSource.ADMIN_PANEL,
        )
        if checkin.status == CheckinStatus.CONFIRMED:
            flash("Jogadora reinserida na lista de confirmadas.", "alert-success")
        else:
            flash("A lista estava cheia; jogadora reinserida na fila de espera.", "alert-warning")

    db.session.commit()

    return redirect(url_for("main.admin_checkins_sessao", session_id=checkin.game_session_id))
