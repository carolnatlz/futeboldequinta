from datetime import timezone
from zoneinfo import ZoneInfo

from flask import flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models import AccountStatus, Pinnie, User, UserRole

from . import main, now_utc, roles_required


BRAZIL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _format_purchase_submitted_at(value):
    if value is None:
        return "Data não informada"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(BRAZIL_TIMEZONE).strftime("%d/%m/%Y às %H:%M")


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
    usuarios = (
        User.query.join(Pinnie, Pinnie.user_id == User.id)
        .filter(Pinnie.payment_declared.is_not(None))
        .order_by(func.lower(User.name).asc())
        .all()
    )
    return render_template(
        "admin/gestao_coletes.html",
        usuarios=usuarios,
        format_purchase_submitted_at=_format_purchase_submitted_at,
    )


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
