from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField,PasswordField,SubmitField, BooleanField, TextAreaField
from wtforms.validators import DataRequired,Length,Email,EqualTo, ValidationError
from siteprojeto.models import Usuario
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
        usuario = Usuario.query.filter_by(email=email.data).first()
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
    afinidade_html = BooleanField('HTML')
    afinidade_css = BooleanField('CSS')
    afinidade_python = BooleanField('Python')
    afinidade_java = BooleanField('Java')
    afinidade_csharp = BooleanField('C#')
    afinidade_php = BooleanField('PHP')
    afinidade_dotnet = BooleanField('.NET')
    afinidade_angular = BooleanField('Angular')
    afinidade_ionic = BooleanField('Ionic')
    afinidade_flutter = BooleanField('Flutter')
    botao_submit_salvar = SubmitField('Salvar')

    def validate_email(self, email):
        if current_user.email != email.data:
            usuario = Usuario.query.filter_by(email=email.data).first()
            if usuario:
                raise ValidationError('Já existe uma conta com esse email.')

class FormCriarPost(FlaskForm):
    titulo = StringField('Título do Post',validators=[DataRequired(),Length(2,150)])
    descricao_post = TextAreaField('Escreva seu post aqui', validators=[DataRequired()])
    botao_submit = SubmitField('Criar Post')
    botao_submit_salvar = SubmitField('Salvar Edição')
    botao_submit_excluir = SubmitField('Excluir Post')

class FormSearch(FlaskForm):
    searched = StringField('Searched',validators=[DataRequired()])
    submit_search = SubmitField('Submit')