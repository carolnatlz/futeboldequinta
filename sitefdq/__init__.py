#python3.10 -m venv venv
#source venv/bin/activate

#export FLASK_APP=main
#flask run

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail, Message
import os
from sitefdq import routes

app = Flask(__name__)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'cadastro'
login_manager.login_message = 'Quer ver o que está no site? primeiro faça seu cadastro ou login'
login_manager.login_message_category = 'alert-info'

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

database = SQLAlchemy(app)
migrate = Migrate(app, database)