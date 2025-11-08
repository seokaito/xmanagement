import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()  # ローカルで .env を使う場合のみ

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')  # Render の環境変数を使う
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret')

db = SQLAlchemy(app)

@app.route('/')
def index():
    return "✅ Flask (production-ready launch)!"

if __name__ == "__main__":
    app.run(debug=True)

