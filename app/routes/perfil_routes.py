from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import Float, case, cast, func

from app import db
from app.email_auth import EmailDeliveryError, send_email_verification_email
from app.forms import FormEditarPerfil
from app.models import AccountStatus, CheckinStatus, GameCheckin, PlayerPosition, User

from . import (
    ProfileImageUploadError,
    main,
    now_utc,
    remover_imagem,
    salvar_imagem,
)


POSITION_LABELS = {
    PlayerPosition.GOL: "Gol",
    PlayerPosition.DEFESA: "Defesa",
    PlayerPosition.ATAQUE: "Ataque",
}

def _build_profile_stats(user_id):
    attendance_totals = (
        db.session.query(
            func.sum(
                case((GameCheckin.status == CheckinStatus.ATTENDED, 1), else_=0)
            ).label("attended"),
            func.sum(
                case((GameCheckin.status == CheckinStatus.NO_SHOW, 1), else_=0)
            ).label("no_show"),
        )
        .filter(GameCheckin.user_id == user_id)
        .one()
    )

    attended_count = attendance_totals.attended or 0
    no_show_count = attendance_totals.no_show or 0
    resolved_games = attended_count + no_show_count
    presence_pct = round((attended_count / resolved_games) * 100) if resolved_games else 0

    ranking_source = (
        db.session.query(
            GameCheckin.user_id.label("user_id"),
            func.sum(
                case((GameCheckin.status == CheckinStatus.ATTENDED, 1), else_=0)
            ).label("attended_count"),
            func.sum(
                case((GameCheckin.status == CheckinStatus.NO_SHOW, 1), else_=0)
            ).label("no_show_count"),
        )
        .join(User, User.id == GameCheckin.user_id)
        .filter(User.account_status == AccountStatus.APPROVED)
        .group_by(GameCheckin.user_id)
        .having(
            func.sum(
                case(
                    (
                        GameCheckin.status.in_(
                            (CheckinStatus.ATTENDED, CheckinStatus.NO_SHOW)
                        ),
                        1,
                    ),
                    else_=0,
                )
            )
            > 0
        )
        .subquery()
    )

    resolved_count_expr = (
        ranking_source.c.attended_count + ranking_source.c.no_show_count
    )
    presence_ratio_expr = case(
        (
            resolved_count_expr > 0,
            cast(ranking_source.c.attended_count, Float)
            / cast(resolved_count_expr, Float),
        ),
        else_=0.0,
    )

    ranking_query = (
        db.session.query(
            ranking_source.c.user_id,
            func.dense_rank()
            .over(
                order_by=(
                    ranking_source.c.attended_count.desc(),
                    presence_ratio_expr.desc(),
                    ranking_source.c.no_show_count.asc(),
                )
            )
            .label("ranking_position"),
        )
        .subquery()
    )

    ranking_position = (
        db.session.query(ranking_query.c.ranking_position)
        .filter(ranking_query.c.user_id == user_id)
        .scalar()
    )

    return {
        "games": attended_count,
        "presence_pct": presence_pct,
        "ranking_position": ranking_position,
        "ranking_display": f"{ranking_position}º" if ranking_position else "—",
    }


@main.route("/perfil")
@login_required
def perfil():
    return render_template(
        "perfil/perfil.html",
        position_label=POSITION_LABELS.get(current_user.position, "Não informada"),
        profile_stats=_build_profile_stats(current_user.id),
    )


@main.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    form = FormEditarPerfil()

    if form.validate_on_submit():
        uploaded_profile_image = None
        old_public_id = current_user.profile_img_public_id
        if form.foto_perfil.data:
            try:
                uploaded_profile_image = salvar_imagem(form.foto_perfil.data)
            except ProfileImageUploadError as exc:
                flash(
                    f"Não conseguimos salvar sua foto de perfil agora. {exc}",
                    "alert-danger",
                )
                return render_template(
                    "perfil/editar_perfil.html",
                    form=form,
                    position_label=POSITION_LABELS.get(
                        current_user.position, "Não informada"
                    ),
                )

        email_alterado = current_user.email != form.email.data
        current_user.name = form.username.data
        current_user.email = form.email.data
        current_user.phone = form.celular.data
        feedback_message = "Perfil atualizado com sucesso!"
        feedback_category = "alert-success"

        if uploaded_profile_image:
            current_user.profile_img = uploaded_profile_image.url
            current_user.profile_img_public_id = uploaded_profile_image.public_id

        if email_alterado:
            current_user.email_verified_at = None
            current_user.email_verification_sent_at = None

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            if uploaded_profile_image:
                remover_imagem(uploaded_profile_image.public_id)
            current_app.logger.exception(
                "Falha ao persistir atualizacao de perfil para %s.",
                current_user.id,
            )
            flash(
                "Não conseguimos salvar seu perfil agora. Tente novamente em instantes.",
                "alert-danger",
            )
            return render_template(
                "perfil/editar_perfil.html",
                form=form,
                position_label=POSITION_LABELS.get(
                    current_user.position, "Não informada"
                ),
            )

        if (
            uploaded_profile_image
            and old_public_id
            and old_public_id != uploaded_profile_image.public_id
        ):
            remover_imagem(old_public_id)

        if email_alterado:
            try:
                send_email_verification_email(current_user)
            except EmailDeliveryError:
                feedback_message = (
                    "Perfil atualizado, mas não conseguimos enviar a verificação para o novo email agora. "
                    "Tente reenviar o link mais tarde."
                )
                feedback_category = "alert-warning"
            else:
                current_user.email_verification_sent_at = now_utc()
                db.session.commit()
                feedback_message = (
                    "Perfil atualizado! Enviamos um link de verificação para o novo email informado."
                )
                feedback_category = "alert-info"

            logout_user()
            flash(
                "Por segurança, pedimos um novo login depois da troca de email.",
                "alert-info",
            )
            flash(feedback_message, feedback_category)
            return redirect(url_for("main.login"))

        flash(feedback_message, feedback_category)
        return redirect(url_for("main.perfil"))

    if request.method == "GET":
        form.username.data = current_user.name
        form.email.data = current_user.email
        form.celular.data = current_user.phone

    return render_template(
        "perfil/editar_perfil.html",
        form=form,
        position_label=POSITION_LABELS.get(current_user.position, "Não informada"),
    )
