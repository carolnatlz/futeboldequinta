#to import PIL: $pip install Pillow

from ast import For
from pydoc import describe
import secrets
from siteprojeto import app, database, bcrypt
from flask import Flask, render_template, url_for, request, flash, redirect, abort
from siteprojeto.forms import FormCriarConta, FormLogin, FormEditarPerfil, FormCriarPost, FormSearch
from siteprojeto.models import Usuario, Post
from flask_login import login_user, logout_user, current_user, login_required
import os
from PIL import Image
from flask_mail import Mail, Message
from siteprojeto import database

@app.route("/")
def home():
    return render_template('home.html')

@app.route("/contato")
def contato():
    return render_template('contato.html')

@app.route("/usuarios")
@login_required
def usuarios():
    lista_usuarios = Usuario.query.all()
    return render_template('usuarios.html',lista_usuarios=lista_usuarios)

#por padrão já é liberado o método GET
@app.route("/cadastro", methods=['GET','POST'])
def cadastro():
    form_login = FormLogin()
    form_criar_conta = FormCriarConta()

    if form_login.validate_on_submit() and 'botao_submit_login' in request.form:
        usuario = Usuario.query.filter_by(email=form_login.email.data).first()
        #se o usuario existe e a senha está correta:
        if usuario and bcrypt.check_password_hash(usuario.senha,form_login.senha.data):
            login_user(usuario, remember=form_login.lembrar_login.data) #remember recebe um parâmetro de true/false
            flash(f'Login feito com sucesso para o email {form_login.email.data}', 'alert-success')
            parametro_next_redirecionar = request.args.get('next')
            if parametro_next_redirecionar:
                return redirect(parametro_next_redirecionar)
            else:
                return redirect(url_for('home'))
        else:
            flash(f'Falha no login, email ou senha incorretos.','alert-danger')
    if form_criar_conta.validate_on_submit() and 'botao_submit_criarconta' in request.form:
        senha_cript = bcrypt.generate_password_hash(form_criar_conta.senha.data)
        usuario = Usuario(usuario=form_criar_conta.username.data,email=form_criar_conta.email.data,senha=senha_cript)
        database.session.add(usuario)
        database.session.commit()
        flash(f'Email criado com sucesso para o email {form_criar_conta.email.data}', 'alert-success')
        return redirect(url_for('home'))
    return render_template('cadastro.html',form_login=form_login,form_criar_conta=form_criar_conta)

@app.route('/sair')
@login_required
def sair():
    logout_user()
    flash(f'logout feito com sucesso','alert-success')
    return redirect(url_for('home'))

@app.route('/perfil')
@login_required
def perfil():
    foto_perfil = url_for('static',filename='fotos_perfil/{}'.format(current_user.foto_perfil))
    return render_template('perfil.html',foto_perfil=foto_perfil)


def salvar_imagem(imagem):
    codigo = secrets.token_hex(8)
    nome, extensao = os.path.splitext(imagem.filename)
    nome_arquivo = nome + codigo + extensao
    caminho_completo = os.path.join(app.root_path, 'static/fotos_perfil', nome_arquivo)
    tamanho = (200,500)
    imagem_reduzida = Image.open(imagem)
    imagem_reduzida.thumbnail(tamanho)
    imagem_reduzida.save(caminho_completo)
    return nome_arquivo

@app.route('/perfil/editar', methods=['GET','POST'])
@login_required
def editar_perfil():
    form_editarperfil = FormEditarPerfil()
    if form_editarperfil.validate_on_submit():
        current_user.email = form_editarperfil.email.data
        current_user.usuario = form_editarperfil.username.data
        current_user.posicao = 'INSERIR ALGO ANALOGO AO FORM' #AJUSTAR 
        if form_editarperfil.foto_perfil.data:
            nome_imagem = salvar_imagem(form_editarperfil.foto_perfil.data)
            current_user.foto_perfil = nome_imagem
        database.session.commit()
        flash('Perfil atualizado com sucesso!', 'alert-success')
        return redirect(url_for('perfil'))
    elif request.method == "GET":   #verifica se está carregando a página, ou seja, se o método é get
        form_editarperfil.email.data = current_user.email
        form_editarperfil.username.data = current_user.usuario
      


#Para o erro Invalid salt:
'''
Em if usuario and bcrypt.... troque por if usuario and bcrypt.check_password_hash(usuario.senha.decode('utf-8'), form_login.senha.data):
Na criação de conta troque senha_crypt = ... por senha_crypt = bcrypt.generate_password_hash(form_criarconta.senha.data).encode('utf-8')
'''

#Teste para avaliar se a criptografia na criação da senha funcionou:
'''
$ python
>> from siteprojeto import database
>> from siteprojeto.models import Usuario, Post
>> user1 = Usuario.query.filter_by(email='cao@gmail.com').first()
>> user1.senha
b'$2b$12$vve4mzidxHLyaOLmDc5zruV13DS5i3oLh1Llx5WU/GuoKaqgyNOwu'

>> from flask_bcrypt import Bcrypt
>> bcrypt = Bcrypt()
>> senha='123456'
>> senha_cript = bcrypt.generate_password_hash(senha)
>> bcrypt.check_password_hash(user1.senha,senha) ou >> bcrypt.check_password_hash(user1.senha,'123456')
True
'''

#Para consultar a base de dados:
'''
sqlite3 siteprojeto.db

sqlite> .schema
sqlite> .excel
sqlite> SELECT * FROM usuario;
'''


