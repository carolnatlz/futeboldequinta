from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField,PasswordField,SubmitField, BooleanField, TextAreaField
from wtforms.validators import DataRequired,Length,Email,EqualTo, ValidationError
from app.models import User
from flask_login import current_user

#from django.core.exceptions import ValidationError
#pip install django-core

class FormCriarConta(FlaskForm):
    username = StringField('Nome de Usuário',validators=[DataRequired()])
    email = StringField('Email',validators=[DataRequired(),Email()])
    senha = PasswordField('Senha',validators=[DataRequired(),Length(6,20)])
    confirmacao = PasswordField('Confirmação da Senha',validators=[DataRequired(),EqualTo('senha')])
    botao_submit_criarconta = SubmitField('Criar Conta')

    #a classe precisa ser validate para que o python identifique que precisa rodá-la automaticamente:

    def validate_email(self, email):
        usuario = User.query.filter_by(email=email.data).first()
        if usuario:
            raise ValidationError('O email já foi cadastrado.')

class FormLogin(FlaskForm):
    email = StringField('Email',validators=[DataRequired(),Email(message="digite um endereço de email válido")])
    senha = PasswordField('Senha',validators=[DataRequired(),Length(6,20)])
    lembrar_login = BooleanField('Lembrar Dados de Acesso')
    botao_submit_login = SubmitField('Fazer Login')

class FormEditarPerfil(FlaskForm):
    username = StringField('Nome de Usuário',validators=[DataRequired()])
    email = StringField('Email',validators=[DataRequired(),Email()])
    foto_perfil = FileField('Atualizar foto de perfil',validators=[FileAllowed(['jpg','png'])])
    botao_submit_salvar = SubmitField('Salvar')

    def validate_email(self, email):
        if current_user.email != email.data:
            usuario = User.query.filter_by(email=email.data).first()
            if usuario:
                raise ValidationError('Já existe uma conta com esse email.')