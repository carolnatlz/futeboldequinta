#o init é o arquivo de inicialização, caso precisasse de outro bastava escrever: from siteprojeto.nomedoarquivo
# export FLASK_APP=zmain.py
# flask run --host=0.0.0.0 --port=8000
 
from siteprojeto import app

if __name__ == '__zmain__':
    app.run(debug=True)

''' 
Abrir o terminal para configurar o email e nome no git:
$ git config --global user.email "carolina.natalizi@gmail.com"
$ git config --global user.name "carolnatlz"

conforme etapas do site (https://dashboard.heroku.com/apps/deployscarol/deploy/heroku-git):
$ heroku login
$ git init
$ heroku git:remote -a deployscarol
    set git remote heroku to https://git.heroku.com/deployscarol.git
    $ pip install gunicorn

salvar um arquivo com nome 'Procfile' que não tenha extensão contendo dentro somente o texto: 
web: gunicorn zmain:app

será necessário passar pro servidor o nome e a versão de todas as bibliotecas usadas no projeto 
usando o comando pip freeze e salvando como um txt:
$ pip freeze > requirements.txt

$ git add .
$ git commit -am "deploy inicial"
$ git push heroku master
'''

