from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from app import db
from app.models import AccountStatus, User, UserRole

from . import main, now_utc, roles_required


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
