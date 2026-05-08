from flask_login import current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from sqlalchemy import func
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError

from app.models import User

from .auth_forms import normalize_email


class FormEditarPerfil(FlaskForm):
    username = StringField("Nome de Usuário", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()], filters=[normalize_email])
    foto_perfil = FileField("Atualizar foto de perfil", validators=[FileAllowed(["jpg", "png"])])
    botao_submit_salvar = SubmitField("Salvar")

    def validate_email(self, email):
        current_email = (current_user.email or "").strip().lower()
        if current_email != email.data:
            usuario = User.query.filter(func.lower(User.email) == email.data).first()
            if usuario:
                raise ValidationError("Já existe uma conta com esse email.")

