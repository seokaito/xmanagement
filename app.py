from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Render の PostgreSQL 接続情報を環境変数から取得
import os
DB_URL = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ------------------------------
# Models
# ------------------------------
class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150))
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='active')
    hired_at = db.Column(db.Date)
    terminated_at = db.Column(db.Date)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer)
    employee_id = db.Column(db.Integer)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default='staff')

# ------------------------------
# Routes
# ------------------------------
@app.route("/employees")
def get_employees():
    employees = Employee.query.all()
    result = []
    for e in employees:
        result.append({
            "id": e.id,
            "name": e.name,
            "email": e.email,
            "employee_code": e.employee_code
        })
    return jsonify(result)

@app.route("/users")
def get_users():
    users = User.query.all()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "employee_id": u.employee_id
        })
    return jsonify(result)

# ------------------------------
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
