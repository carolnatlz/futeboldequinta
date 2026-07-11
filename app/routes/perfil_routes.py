from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import Float, case, cast, func
from sqlalchemy.exc import IntegrityError

from app import db
from app.email_auth import EmailDeliveryError, send_email_verification_email
from app.forms import FormEditarPerfil
from app.models import (
    AccountStatus,
    CheckinStatus,
    GameCheckin,
    Pinnie,
    PlayerPosition,
    User,
)

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

PINNIE_NAME_MAX_LENGTH = 20
PINNIE_NUMBER_MIN = 1
PINNIE_NUMBER_MAX = 999


def _build_available_pinnie_numbers(current_pinnie=None):
    occupied_numbers_query = db.session.query(Pinnie.pinnie_number)
    if current_pinnie:
        occupied_numbers_query = occupied_numbers_query.filter(Pinnie.id != current_pinnie.id)

    occupied_numbers = {number for number, in occupied_numbers_query.all()}
    return [
        number
        for number in range(PINNIE_NUMBER_MIN, PINNIE_NUMBER_MAX + 1)
        if number not in occupied_numbers
    ]


def _parse_selected_pinnie_number(raw_value):
    raw_value = (raw_value or "").strip()
    return int(raw_value) if raw_value.isdigit() else None


def _render_coletes_teste_page(*, current_pinnie, form_data=None):
    if form_data is None:
        selected_pinnie_name = current_pinnie.pinnie_name if current_pinnie else ""
        selected_pinnie_number = current_pinnie.pinnie_number if current_pinnie else None
    else:
        selected_pinnie_name = (form_data.get("pinnie_name") or "").strip()
        selected_pinnie_number = _parse_selected_pinnie_number(form_data.get("pinnie_number"))

    available_pinnie_numbers = _build_available_pinnie_numbers(current_pinnie)
    if selected_pinnie_number not in available_pinnie_numbers:
        selected_pinnie_number = None

    return render_template(
        "perfil/coletes_teste.html",
        current_pinnie=current_pinnie,
        available_pinnie_numbers=available_pinnie_numbers,
        pinnie_name_max_length=PINNIE_NAME_MAX_LENGTH,
        selected_pinnie_name=selected_pinnie_name,
        selected_pinnie_number=selected_pinnie_number,
    )

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


@main.route("/coletes-teste", methods=["GET", "POST"])
@login_required
def coletes_teste():
    current_pinnie = current_user.pinnie

    if request.method == "POST":
        pinnie_name = (request.form.get("pinnie_name") or "").strip()
        pinnie_number = _parse_selected_pinnie_number(request.form.get("pinnie_number"))
        has_error = False

        if not pinnie_name:
            flash(
                "Informe o nome que será escrito no colete.",
                "alert-danger",
            )
            has_error = True
        elif len(pinnie_name) > PINNIE_NAME_MAX_LENGTH:
            flash(
                f"O nome do colete pode ter no máximo {PINNIE_NAME_MAX_LENGTH} caracteres.",
                "alert-danger",
            )
            has_error = True

        if pinnie_number is None:
            flash(
                "Escolha um número de colete disponível.",
                "alert-danger",
            )
            has_error = True
        elif not PINNIE_NUMBER_MIN <= pinnie_number <= PINNIE_NUMBER_MAX:
            flash(
                f"O número do colete deve estar entre {PINNIE_NUMBER_MIN} e {PINNIE_NUMBER_MAX}.",
                "alert-danger",
            )
            has_error = True
        else:
            conflicting_pinnie = Pinnie.query.filter(Pinnie.pinnie_number == pinnie_number)
            if current_pinnie:
                conflicting_pinnie = conflicting_pinnie.filter(Pinnie.id != current_pinnie.id)

            if conflicting_pinnie.first():
                flash(
                    "Esse número de colete não está mais disponível. Escolha outro.",
                    "alert-danger",
                )
                has_error = True

        if has_error:
            return _render_coletes_teste_page(
                current_pinnie=current_pinnie,
                form_data=request.form,
            )

        if current_pinnie:
            current_pinnie.pinnie_name = pinnie_name
            current_pinnie.pinnie_number = pinnie_number
        else:
            db.session.add(
                Pinnie(
                    user_id=current_user.id,
                    pinnie_name=pinnie_name,
                    pinnie_number=pinnie_number,
                )
            )

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Esse número acabou de ser reservado por outra jogadora. Escolha outro e tente novamente.",
                "alert-danger",
            )
            return _render_coletes_teste_page(
                current_pinnie=current_user.pinnie,
                form_data=request.form,
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Falha ao persistir solicitacao de colete para %s.",
                current_user.id,
            )
            flash(
                "Não conseguimos salvar sua solicitação de colete agora. Tente novamente em instantes.",
                "alert-danger",
            )
            return _render_coletes_teste_page(
                current_pinnie=current_user.pinnie,
                form_data=request.form,
            )

        flash("Solicitação de colete salva com sucesso.", "alert-success")
        return redirect(url_for("main.coletes_teste"))

    return _render_coletes_teste_page(current_pinnie=current_pinnie)


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
