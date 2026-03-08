from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, PasswordField, SubmitField, BooleanField, RadioField
from wtforms.validators import DataRequired,Length,Email,EqualTo, ValidationError
from app.models import User
from flask_login import current_user
from sqlalchemy import func

#from django.core.exceptions import ValidationError
#pip install django-core


def normalize_email(value):
    if not value:
        return value
    return value.strip().lower()

class FormCriarConta(FlaskForm):
    username = StringField('Nome de Usuário', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()], filters=[normalize_email])
    celular = StringField('Celular', validators=[DataRequired(), Length(min=10, max=20)])
    senha = PasswordField('Senha', validators=[DataRequired(), Length(6,20)])
    confirmacao = PasswordField('Confirmação da Senha', validators=[DataRequired(), EqualTo('senha')])
    foto_perfil = FileField(
        'Escolher foto',
        validators=[
            FileRequired(message='Escolha uma foto de perfil.'),
            FileAllowed(['jpg', 'jpeg', 'png'], 'Apenas JPG ou PNG.')
        ]
    )
    position = RadioField(
        'Posição',
        choices=[
            ('gol', 'Gol'),
            ('defesa', 'Defesa'),
            ('ataque', 'Ataque')
        ],
        validators=[DataRequired(message='Selecione sua posição.')]
    )
    botao_submit_criarconta = SubmitField('Entrar')

    #a classe precisa ser validate para que o python identifique que precisa rodá-la automaticamente:

    def validate_email(self, email):
        usuario = User.query.filter(func.lower(User.email) == email.data).first()
        if usuario:
            raise ValidationError('O email já foi cadastrado.')

    def validate_celular(self, celular):
        usuario = User.query.filter_by(phone=celular.data).first()
        if usuario:
            raise ValidationError('O celular já foi cadastrado.')

class FormLogin(FlaskForm):
    email = StringField('Email',validators=[DataRequired(),Email(message="digite um endereço de email válido")], filters=[normalize_email])
    senha = PasswordField('Senha',validators=[DataRequired(),Length(6,20)])
    lembrar_login = BooleanField('Lembrar Dados de Acesso')
    botao_submit_login = SubmitField('Fazer Login')

class FormEditarPerfil(FlaskForm):
    username = StringField('Nome de Usuário',validators=[DataRequired()])
    email = StringField('Email',validators=[DataRequired(),Email()], filters=[normalize_email])
    foto_perfil = FileField('Atualizar foto de perfil',validators=[FileAllowed(['jpg','png'])])
    botao_submit_salvar = SubmitField('Salvar')

    def validate_email(self, email):
        current_email = (current_user.email or "").strip().lower()
        if current_email != email.data:
            usuario = User.query.filter(func.lower(User.email) == email.data).first()
            if usuario:
                raise ValidationError('Já existe uma conta com esse email.')
