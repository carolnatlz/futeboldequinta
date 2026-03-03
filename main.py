from app import create_app
app = create_app()


'''
source venv/bin/activate
flask db migrate
flask db upgrade
pip freeze > requirements.txt
git status (para ver todas as mudanças que vão subir)

git add .
git commit -m "descrição"
git push
'''

# flask --app main run --host=0.0.0.0 --port=8000