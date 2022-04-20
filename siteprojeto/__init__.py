#python3.10 -m venv venv
#source venv/bin/activate

#export FLASK_APP=zmain
#flask run

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate

app = Flask(__name__)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'cadastro'
login_manager.login_message = 'Quer ver o que está no site? primeiro faça seu cadastro ou login'
login_manager.login_message_category = 'alert-info'

#para importar um token > abra o terminal e digite python
#>import secrets
#>secrets.token_hex(16)
app.config['SECRET_KEY']='52aeaae54c8e77eee57b9ab614946083'
app.config['SQLALCHEMY_DATABASE_URI']= 'sqlite:///siteprojeto.db'

database = SQLAlchemy(app)
migrate = Migrate(app, database)

from siteprojeto import routes