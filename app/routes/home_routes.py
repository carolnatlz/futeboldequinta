from flask import render_template
from app.routes import main

SEQUENCIA_DOS_JOGOS = [
    {"rodada": 1, "jogos": ["A x B", "C x D", "E x F"]},
    {"rodada": 2, "jogos": ["A x C", "B x E", "D x F"]},
    {"rodada": 3, "jogos": ["B x C", "F x A", "E x D"]},
    {"rodada": 4, "jogos": ["F x B", "C x E", "D x A"]},
]


@main.route("/")
@main.route("/home")
def home():
    return render_template("components/home.html")


@main.route("/agenda")
def agenda():
    return render_template("components/agenda.html")


@main.route("/sequencia-dos-jogos")
def sequencia_dos_jogos():
    return render_template(
        "components/sequencia_dos_jogos.html",
        rodadas=SEQUENCIA_DOS_JOGOS,
    )


@main.route("/regras")
def regras():
    return render_template("components/regras.html")
