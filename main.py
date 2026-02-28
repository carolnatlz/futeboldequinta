 
from sitefdq import app

if __name__ == '__main__':
    app.run(debug=True)


# export FLASK_APP=main.py
# flask run --host=0.0.0.0 --port=8000
# ativar venv: source venv/bin/activate no MAC

'''
pip freeze > requirements.txt
git add requirements.txt
git commit -m "update requirements"
git push
gunicorn main:app
'''
