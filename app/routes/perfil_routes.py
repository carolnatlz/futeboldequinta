from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import FormEditarPerfil

from . import main, salvar_imagem


@main.route("/perfil")
@login_required
def perfil():
    foto = (
        url_for("static", filename=f"img/fotos_perfil/{current_user.profile_img}")
        if current_user.profile_img
        else url_for("static", filename="img/fotos_perfil/default.jpg")
    )
    return render_template("perfil/perfil.html", foto_perfil=foto)


@main.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def editar_perfil():
    form = FormEditarPerfil()

    if form.validate_on_submit():
        current_user.name = form.username.data
        current_user.email = form.email.data

        if form.foto_perfil.data:
            nome_imagem = salvar_imagem(form.foto_perfil.data)
            current_user.profile_img = nome_imagem

        db.session.commit()

        flash("Perfil atualizado com sucesso!", "alert-success")
        return redirect(url_for("main.perfil"))

    if request.method == "GET":
        form.username.data = current_user.name
        form.email.data = current_user.email

    return render_template("perfil/editar_perfil.html", form=form)

