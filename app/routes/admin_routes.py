from datetime import timezone
from zoneinfo import ZoneInfo

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.models import AccountStatus, Pinnie, PinnieSettings, User, UserRole

from . import main, now_utc, roles_required


BRAZIL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
PINNIE_SETTINGS_ID = 1
MAX_PINNIE_BATCH_NUMBER = 2_147_483_647


def _format_purchase_submitted_at(value):
    if value is None:
        return "Data não informada"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(BRAZIL_TIMEZONE).strftime("%d/%m/%Y às %H:%M")


def _pinnie_control_eligible_filter():
    return or_(
        Pinnie.payment_declared.is_(True),
        Pinnie.deposit_paid_at.is_not(None),
        Pinnie.payment_completed_at.is_not(None),
        Pinnie.pinnie_delivered_at.is_not(None),
    )


def _pinnie_control_group(pinnie):
    if pinnie.pinnie_delivered_at is not None:
        return "finalizados"
    if pinnie.payment_completed_at is not None:
        return "entrega"
    return "pagamentos"


@main.route("/admin/aprovacoes")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_aprovacoes():
    pendentes = (
        User.query.filter(
            User.role == UserRole.PLAYER,
            User.account_status == AccountStatus.PENDING,
        )
        .order_by(User.created_at.asc())
        .all()
    )
    return render_template("admin/aprovacoes.html", usuarios=pendentes)


@main.route("/admin/rejeitados")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_rejeitados():
    rejeitados = (
        User.query.filter(
            User.role == UserRole.PLAYER,
            User.account_status == AccountStatus.REJECTED,
        )
        .order_by(User.updated_at.desc())
        .all()
    )
    return render_template("admin/rejeitados.html", usuarios=rejeitados)


@main.route("/admin/usuarios")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_usuarios():
    usuarios = User.query.order_by(func.lower(User.name).asc()).all()
    return render_template("admin/usuarios.html", usuarios=usuarios)


@main.route("/admin/gestao-coletes")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_gestao_coletes():
    pinnie_settings = PinnieSettings.query.get_or_404(PINNIE_SETTINGS_ID)
    usuarios = (
        User.query.join(Pinnie, Pinnie.user_id == User.id)
        .filter(Pinnie.payment_declared.is_(True))
        .order_by(func.lower(User.name).asc())
        .all()
    )
    usuarios_pagamentos = (
        User.query.join(Pinnie, Pinnie.user_id == User.id)
        .filter(
            _pinnie_control_eligible_filter(),
            Pinnie.payment_completed_at.is_(None),
            Pinnie.pinnie_delivered_at.is_(None),
        )
        .order_by(func.lower(User.name).asc())
        .all()
    )
    usuarios_entrega = (
        User.query.join(Pinnie, Pinnie.user_id == User.id)
        .filter(
            Pinnie.payment_completed_at.is_not(None),
            Pinnie.pinnie_delivered_at.is_(None),
        )
        .order_by(func.lower(User.name).asc())
        .all()
    )
    usuarios_finalizados = (
        User.query.join(Pinnie, Pinnie.user_id == User.id)
        .filter(Pinnie.pinnie_delivered_at.is_not(None))
        .order_by(func.lower(User.name).asc())
        .all()
    )
    return render_template(
        "admin/gestao_coletes.html",
        usuarios=usuarios,
        usuarios_pagamentos=usuarios_pagamentos,
        usuarios_entrega=usuarios_entrega,
        usuarios_finalizados=usuarios_finalizados,
        current_batch_number=pinnie_settings.current_batch_number,
        is_admin_view=current_user.role == UserRole.ADMIN,
        format_purchase_submitted_at=_format_purchase_submitted_at,
    )


@main.route("/admin/gestao-coletes/remessa-atual", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN)
def admin_atualizar_remessa_atual():
    raw_batch_number = (request.form.get("current_batch_number") or "").strip()

    try:
        batch_number = int(raw_batch_number)
    except ValueError:
        batch_number = 0

    if not 1 <= batch_number <= MAX_PINNIE_BATCH_NUMBER:
        flash("Informe um número de remessa válido e maior que zero.", "alert-danger")
        return redirect(url_for("main.admin_gestao_coletes"))

    pinnie_settings = PinnieSettings.query.get_or_404(PINNIE_SETTINGS_ID)
    if pinnie_settings.current_batch_number == batch_number:
        flash(f"A remessa atual já é a Remessa {batch_number}.", "alert-info")
        return redirect(url_for("main.admin_gestao_coletes"))

    pinnie_settings.current_batch_number = batch_number
    pinnie_settings.updated_at = now_utc()
    db.session.commit()

    flash(f"Remessa atual alterada para Remessa {batch_number}.", "alert-success")
    return redirect(url_for("main.admin_gestao_coletes"))


@main.route(
    "/admin/gestao-coletes/<uuid:pinnie_id>/etapas/<action>/<stage>",
    methods=["POST"],
)
@login_required
@roles_required(UserRole.ADMIN)
def admin_atualizar_etapa_colete(pinnie_id, action, stage):
    pinnie = Pinnie.query.get_or_404(pinnie_id)
    player_name = pinnie.user.name if pinnie.user else f"Colete {pinnie.pinnie_number}"
    transition_message = None
    transition_category = "alert-success"

    if action == "confirmar" and stage == "sinal":
        if (
            pinnie.payment_declared is True
            and pinnie.deposit_paid_at is None
            and pinnie.payment_completed_at is None
            and pinnie.pinnie_delivered_at is None
        ):
            pinnie.deposit_paid_at = now_utc()
            transition_message = f"Sinal de {player_name} confirmado."
    elif action == "confirmar" and stage == "quitacao":
        if (
            pinnie.deposit_paid_at is not None
            and pinnie.payment_completed_at is None
            and pinnie.pinnie_delivered_at is None
        ):
            if pinnie.pinnie_batch_number is None:
                pinnie_settings = PinnieSettings.query.get_or_404(PINNIE_SETTINGS_ID)
                pinnie.pinnie_batch_number = pinnie_settings.current_batch_number

            pinnie.payment_completed_at = now_utc()
            transition_message = (
                f"Quitação de {player_name} confirmada na "
                f"Remessa {pinnie.pinnie_batch_number}."
            )
    elif action == "confirmar" and stage == "entrega":
        if (
            pinnie.payment_completed_at is not None
            and pinnie.pinnie_delivered_at is None
        ):
            pinnie.pinnie_delivered_at = now_utc()
            transition_message = f"Entrega do colete de {player_name} confirmada."
    elif action == "desfazer" and stage == "entrega":
        if pinnie.pinnie_delivered_at is not None:
            pinnie.pinnie_delivered_at = None
            transition_message = f"Entrega do colete de {player_name} desfeita."
            transition_category = "alert-warning"
    elif action == "desfazer" and stage == "quitacao":
        if (
            pinnie.pinnie_delivered_at is None
            and pinnie.payment_completed_at is not None
        ):
            pinnie.payment_completed_at = None
            transition_message = (
                f"Quitação de {player_name} desfeita; a remessa atribuída foi preservada."
            )
            transition_category = "alert-warning"
    elif action == "desfazer" and stage == "sinal":
        if (
            pinnie.pinnie_delivered_at is None
            and pinnie.payment_completed_at is None
            and pinnie.deposit_paid_at is not None
        ):
            pinnie.deposit_paid_at = None
            transition_message = f"Confirmação do sinal de {player_name} desfeita."
            transition_category = "alert-warning"

    if transition_message is not None:
        db.session.commit()

    response_message = transition_message or (
        "Essa etapa já foi alterada ou não respeita a ordem do fluxo."
    )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        row_html = ""
        if pinnie.user is not None:
            row_html = render_template(
                "admin/_pinnie_control_row.html",
                usuario=pinnie.user,
                is_admin_view=True,
                format_purchase_submitted_at=_format_purchase_submitted_at,
            )

        return jsonify(
            success=transition_message is not None,
            message=response_message,
            category=(transition_category if transition_message else "alert-info"),
            target_group=_pinnie_control_group(pinnie),
            row_html=row_html,
        )

    flash(
        response_message,
        transition_category if transition_message else "alert-info",
    )

    return redirect(url_for("main.admin_gestao_coletes"))


@main.route("/admin/aprovacoes/<uuid:user_id>/aceitar", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_aceitar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    usuario.account_status = AccountStatus.APPROVED
    usuario.updated_at = now_utc()
    db.session.commit()

    flash(f"Usuário {usuario.name} aprovado com sucesso.", "alert-success")
    return redirect(url_for("main.admin_aprovacoes"))


@main.route("/admin/aprovacoes/<uuid:user_id>/rejeitar", methods=["POST"])
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def admin_rejeitar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    usuario.account_status = AccountStatus.REJECTED
    usuario.updated_at = now_utc()
    db.session.commit()

    flash(f"Usuário {usuario.name} movido para rejeitados.", "alert-warning")
    return redirect(url_for("main.admin_rejeitados"))
