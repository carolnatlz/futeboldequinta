from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from sqlalchemy import func
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, ValidationError

from app.models import User

from .auth_forms import normalize_email


class FormEditarPerfil(FlaskForm):
    username = StringField("Nome de Usuário", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()], filters=[normalize_email])
    celular = StringField("Celular", validators=[DataRequired(), Length(min=10, max=20)])
    position = RadioField(
        "Posição",
        choices=[
            ("gol", "Gol"),
            ("defesa", "Defesa"),
            ("ataque", "Ataque"),
        ],
        validators=[DataRequired(message="Selecione sua posição.")],
    )
    foto_perfil = FileField(
        "Atualizar foto de perfil",
        validators=[FileAllowed(["jpg", "jpeg", "png", "heic"], "Apenas JPG, PNG ou HEIC.")],
    )
    botao_submit_salvar = SubmitField("Salvar")

    def validate_email(self, email):
        current_email = (current_user.email or "").strip().lower()
        if current_email != email.data:
            usuario = User.query.filter(func.lower(User.email) == email.data).first()
            if usuario:
                raise ValidationError("Já existe uma conta com esse email.")

    def validate_celular(self, celular):
        current_phone = (current_user.phone or "").strip()
        if current_phone != celular.data:
            usuario = User.query.filter_by(phone=celular.data).first()
            if usuario:
                raise ValidationError("O celular já foi cadastrado.")
