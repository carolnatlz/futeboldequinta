 
from sitefdq import app

if __name__ == '__main__':
    app.run(debug=True)


# export FLASK_APP=main.py
# flask run --host=0.0.0.0 --port=8000
# ativar venv: source venv/bin/activate no MAC

'''
pip freeze > requirements.txt
gunicorn main:app
git status (para ver todas as mudanças que vão subir)

git add .
git commit -m "descrição"
git push
'''
