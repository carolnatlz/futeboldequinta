from datetime import datetime

from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

from app import db
from app.models import (
    AccountStatus,
    CheckinStatus,
    GameCheckin,
    GameSession,
    GameSessionStatus,
    User,
    UserRole,
)
from app.models.game_sessions import BRAZIL_TZ

from . import main, now_utc, roles_required


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

SESSION_STATUS_LABELS = {
    GameSessionStatus.SCHEDULED: "Agendado",
    GameSessionStatus.OPEN: "Check-in aberto",
    GameSessionStatus.CLOSED: "Jogo em Andamento",
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


def _local_now():
    return datetime.now(BRAZIL_TZ)


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
                    GameCheckin(
                        game_session=session,
                        user=user,
                        status=CheckinStatus.RESERVED,
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
    return waitlisted


def _session_status_badge(status):
    if status == GameSessionStatus.OPEN:
        return "checkin-badge-open"
    if status == GameSessionStatus.CLOSED:
        return "checkin-badge-closed"
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


def _position_label(user):
    if not user.position:
        return "Sem posição"
    return POSITION_LABELS.get(user.position.value, user.position.value.capitalize())


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
        "profile_img_url": (
            url_for("static", filename=f"img/fotos_perfil/{checkin.user.profile_img}")
            if checkin.user.profile_img
            else url_for("static", filename="img/fotos_perfil/default.jpg")
        ),
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
        "window_label": f"Check-in aberto até {session.checkin_closes_at.strftime('%-Hh')}",
    }


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
        .join(User)
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
def meus_checkins():
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

    return render_template("checkins/meus_checkins.html", session_cards=session_cards)


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
        return redirect(url_for("main.meus_checkins"))

    if existing_checkin and existing_checkin.status != CheckinStatus.CANCELLED:
        flash("Você já possui check-in ativo para essa sessão.", "alert-info")
        return redirect(url_for("main.meus_checkins"))

    new_status = (
        CheckinStatus.CONFIRMED
        if _occupied_count(session.id) < session.max_players
        else CheckinStatus.WAITLIST
    )

    if existing_checkin:
        existing_checkin.status = new_status
        existing_checkin.checked_in_at = now_utc()
        existing_checkin.cancelled_at = None
    else:
        db.session.add(
            GameCheckin(
                game_session=session,
                user=current_user,
                status=new_status,
            )
        )

    db.session.commit()

    if new_status == CheckinStatus.CONFIRMED:
        flash("Seu check-in foi confirmado com sucesso.", "alert-success")
    else:
        flash("As vagas confirmadas esgotaram. Você entrou na lista de espera.", "alert-warning")

    return redirect(url_for("main.meus_checkins"))


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
        return redirect(url_for("main.meus_checkins"))

    was_occupying_slot = checkin.status in OCCUPIED_CHECKIN_STATUSES
    checkin.status = CheckinStatus.CANCELLED
    checkin.cancelled_at = now_utc()

    promoted = _promote_waitlist(session.id) if was_occupying_slot else None
    db.session.commit()

    if promoted:
        flash("Check-in cancelado e a primeira pessoa da fila foi promovida automaticamente.", "alert-info")
    else:
        flash("Check-in cancelado com sucesso.", "alert-success")

    return redirect(url_for("main.meus_checkins"))


@main.route("/admin/check-ins")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_checkins():
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
    confirmed_counts = {}
    waitlist_counts = {}

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

    session_cards = [
        {
            "session": session,
            "confirmed_count": confirmed_counts.get(session.id, 0),
            "waitlist_count": waitlist_counts.get(session.id, 0),
            "status_label": SESSION_STATUS_LABELS[session.status],
            "status_badge": _session_status_badge(session.status),
            "display_date": f"{WEEKDAY_LABELS[session.game_date.weekday()]}, {session.game_date.strftime('%d/%m/%Y')}",
            "weekday_label": WEEKDAY_LABELS[session.game_date.weekday()],
            "date_label": session.game_date.strftime('%d/%m/%Y'),
        }
        for session in sessions
    ]

    return render_template("admin/gestao_dos_jogos.html", session_cards=session_cards)


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
        .join(User)
        .order_by(CHECKIN_STATUS_ORDER, GameCheckin.checked_in_at.asc(), User.name.asc())
        .all()
    )

    confirmed_count = sum(1 for checkin in checkins if checkin.status in OCCUPIED_CHECKIN_STATUSES)
    waitlist_count = sum(1 for checkin in checkins if checkin.status == CheckinStatus.WAITLIST)

    return render_template(
        "checkins/checkin_sessao.html",
        session=session,
        checkins=checkins,
        confirmed_count=confirmed_count,
        waitlist_count=waitlist_count,
        checkin_status_labels=CHECKIN_STATUS_LABELS,
        session_status_labels=SESSION_STATUS_LABELS,
    )


@main.route("/admin/check-ins/<uuid:checkin_id>/status/<status_name>", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_atualizar_status_checkin(checkin_id, status_name):
    checkin = GameCheckin.query.get_or_404(checkin_id)
    session = GameSession.query.get_or_404(checkin.game_session_id)
    previous_status = checkin.status

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
        if previous_status in OCCUPIED_CHECKIN_STATUSES:
            _promote_waitlist(checkin.game_session_id)
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
        if checkin.status == CheckinStatus.CONFIRMED:
            flash("Jogadora reinserida na lista de confirmadas.", "alert-success")
        else:
            flash("A lista estava cheia; jogadora reinserida na fila de espera.", "alert-warning")

    db.session.commit()

    return redirect(url_for("main.admin_checkins_sessao", session_id=checkin.game_session_id))
