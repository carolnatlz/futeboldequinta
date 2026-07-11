from flask import render_template
from flask_login import login_required
from app.models.users import UserRole
from app.routes import main, roles_required

SEQUENCIA_DOS_JOGOS = [
    {"rodada": 1, "jogos": ["A x B", "C x D", "E x F"]},
    {"rodada": 2, "jogos": ["A x C", "B x E", "D x F"]},
    {"rodada": 3, "jogos": ["B x C", "F x A", "E x D"]},
    {"rodada": 4, "jogos": ["F x B", "C x E", "D x A"]},
]


@main.route("/")
@main.route("/home")
def nossa_historia():
    return render_template("components/nossa_historia.html")


@main.route("/agenda")
@main.route("/locais-horarios")
def locais_horarios():
    return render_template("components/locais_horarios.html")


@main.route("/sequencia-dos-jogos")
@login_required
def sequencia_dos_jogos():
    return render_template(
        "components/sequencia_dos_jogos.html",
        rodadas=SEQUENCIA_DOS_JOGOS,
    )


@main.route("/quem-ta-jogando-agora")
@login_required
@roles_required(UserRole.ADMIN, UserRole.ORGANIZER)
def quem_ta_jogando_agora():
    return render_template("components/quem_ta_jogando_agora.html")


@main.route("/regras")
def regras():
    return render_template("components/regras.html")
