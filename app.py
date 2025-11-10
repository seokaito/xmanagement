"""
バックエンド更新版（新しいグループフローに対応）

主な変更点：
1. Groupモデルに group_code フィールドを追加
2. グループコードで検索するAPI追加
3. グループに参加するAPI追加
4. UserとGroupの関連を管理
"""

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import traceback
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt
)
import string
import random

# ================================
# 🔹 環境変数読み込み
# ================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# ================================
# 🔹 CORS設定（重要！）
# ================================
CORS(app, resources={
    r"/*": {
        "origins": "*",  # 本番環境では具体的なドメインを指定してください
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ================================
# 🔹 設定
# ================================
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get("JWT_SECRET_KEY", "super-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ================================
# 🔹 モデル（更新版）
# ================================
class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150))


class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)  # ← 新規追加
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # ← User IDに変更
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    creator = db.relationship('User', backref='created_groups', foreign_keys=[created_by])


class GroupMembership(db.Model):
    __tablename__ = 'group_memberships'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # ← employee_id から変更
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    role = db.Column(db.String(20), default='employee')  # 'admin' or 'employee'
    joined_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship('User', backref='group_memberships', lazy=True)
    group = db.relationship('Group', backref='memberships', lazy=True)


class Shift(db.Model):
    __tablename__ = 'shifts'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    employee = db.relationship('Employee', backref=db.backref('shifts', lazy=True))
    group = db.relationship('Group', backref=db.backref('shifts', lazy=True))


class Availability(db.Model):
    __tablename__ = 'availabilities'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    comment = db.Column(db.String(255))


class WageRate(db.Model):
    __tablename__ = 'wage_rates'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    hourly_rate = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(255))
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    group = db.relationship('Group', backref=db.backref('wage_rates', lazy=True))


class ShiftSwap(db.Model):
    __tablename__ = 'shift_swaps'
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    shift = db.relationship('Shift', backref=db.backref('swap_request', lazy=True))
    requester = db.relationship('Employee', backref=db.backref('swap_requests', lazy=True))


class ShiftResponse(db.Model):
    __tablename__ = 'shift_responses'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('shift_requests.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    preferred_date = db.Column(db.Date, nullable=True)
    preferred_start = db.Column(db.Time, nullable=True)
    preferred_end = db.Column(db.Time, nullable=True)
    comment = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    request = db.relationship('ShiftRequest', backref=db.backref('responses', lazy=True))
    employee = db.relationship('Employee', backref=db.backref('responses', lazy=True))


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default="employee")  # ← "teacher" から "employee" に変更

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class ShiftHistory(db.Model):
    __tablename__ = 'shift_histories'
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=False)
    old_employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    new_employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    changed_by = db.Column(db.String(100))
    changed_at = db.Column(db.DateTime, server_default=db.func.now())

    shift = db.relationship('Shift', foreign_keys=[shift_id])
    old_employee = db.relationship('Employee', foreign_keys=[old_employee_id])
    new_employee = db.relationship('Employee', foreign_keys=[new_employee_id])


class ShiftRequest(db.Model):
    __tablename__ = "shift_requests"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    group = db.relationship("Group", backref=db.backref("shift_requests", lazy=True))
    creator = db.relationship("User", backref=db.backref("created_shift_requests", lazy=True))


# ================================
# 🔹 ヘルパー関数
# ================================
def generate_group_code():
    """ランダムなグループコードを生成"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ================================
# 🔹 ルート
# ================================
@app.route("/")
def home():
    return jsonify({"message": "✅ Flask backend is running successfully!"})


# ================================
# 🔹 認証API
# ================================
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email, password, role = data.get("email"), data.get("password"), data.get("role", "employee")
    
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400
    
    user = User(email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    return jsonify({"message": "User registered", "user_id": user.id}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    
    # ユーザーのグループ所属情報を取得
    membership = GroupMembership.query.filter_by(user_id=user.id).first()
    group_code = None
    user_role = user.role
    
    if membership:
        group_code = membership.group.code
        user_role = membership.role  # グループ内での役割を使用
    
    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "email": user.email, 
            "role": user_role,
            "group_code": group_code
        }
    )
    
    return jsonify({
        "access_token": token,
        "group_code": group_code,
        "role": user_role
    }), 200


# ================================
# 🔹 グループAPI（新規・更新）
# ================================
@app.route("/groups", methods=["GET"])
@jwt_required()
def get_groups():
    groups = Group.query.all()
    return jsonify([
        {
            "id": g.id, 
            "name": g.name, 
            "code": g.code,
            "description": g.description,
            "member_count": len(g.memberships)
        }
        for g in groups
    ])


@app.route("/groups", methods=["POST"])
@jwt_required()
def create_group():
    """グループを作成し、作成者を管理者として追加"""
    data = request.get_json()
    name = data.get("name")
    description = data.get("description", "")
    custom_code = data.get("code")  # カスタムコード（オプション）
    
    if not name:
        return jsonify({"error": "Group name is required"}), 400
    
    current_user_id = int(get_jwt_identity())
    
    # グループコードを生成または使用
    if custom_code:
        # カスタムコードの重複チェック
        if Group.query.filter_by(code=custom_code.upper()).first():
            return jsonify({"error": "Group code already exists"}), 400
        group_code = custom_code.upper()
    else:
        # ランダムコードを生成（重複しないまで）
        while True:
            group_code = generate_group_code()
            if not Group.query.filter_by(code=group_code).first():
                break
    
    # グループを作成
    group = Group(
        name=name,
        code=group_code,
        description=description,
        created_by=current_user_id
    )
    db.session.add(group)
    db.session.flush()  # IDを取得するため
    
    # 作成者を管理者としてグループに追加
    membership = GroupMembership(
        user_id=current_user_id,
        group_id=group.id,
        role='admin'
    )
    db.session.add(membership)
    db.session.commit()
    
    return jsonify({
        "message": "Group created successfully",
        "group_id": group.id,
        "group_code": group.code
    }), 201


@app.route("/groups/join", methods=["POST"])
@jwt_required()
def join_group():
    """グループコードでグループに参加"""
    data = request.get_json()
    group_code = data.get("code", "").upper()
    
    if not group_code:
        return jsonify({"error": "Group code is required"}), 400
    
    # グループを検索
    group = Group.query.filter_by(code=group_code).first()
    if not group:
        return jsonify({"error": "Group not found"}), 404
    
    current_user_id = int(get_jwt_identity())
    
    # 既に参加しているかチェック
    existing = GroupMembership.query.filter_by(
        user_id=current_user_id,
        group_id=group.id
    ).first()
    
    if existing:
        return jsonify({"error": "Already a member of this group"}), 400
    
    # グループに参加（employee として）
    membership = GroupMembership(
        user_id=current_user_id,
        group_id=group.id,
        role='employee'
    )
    db.session.add(membership)
    db.session.commit()
    
    return jsonify({
        "message": "Successfully joined the group",
        "group_id": group.id,
        "group_name": group.name,
        "group_code": group.code
    }), 201


@app.route("/groups/my", methods=["GET"])
@jwt_required()
def get_my_groups():
    """自分が所属しているグループ一覧を取得"""
    current_user_id = int(get_jwt_identity())
    
    memberships = GroupMembership.query.filter_by(user_id=current_user_id).all()
    
    return jsonify([
        {
            "group_id": m.group.id,
            "group_name": m.group.name,
            "group_code": m.group.code,
            "role": m.role,
            "joined_at": m.joined_at.isoformat()
        }
        for m in memberships
    ]), 200


# ================================
# 🔹 Employee CRUD
# ================================
@app.route("/employees", methods=["GET"])
def get_employees():
    employees = Employee.query.all()
    return jsonify([
        {"id": e.id, "employee_code": e.employee_code, "name": e.name, "email": e.email}
        for e in employees
    ])


@app.route("/employees", methods=["POST"])
def create_employee():
    data = request.get_json()
    if not data.get("employee_code") or not data.get("name"):
        return jsonify({"error": "employee_code and name are required"}), 400
    new_employee = Employee(**data)
    db.session.add(new_employee)
    db.session.commit()
    return jsonify({"message": "Employee created successfully"}), 201


# ================================
# 🔹 Shift
# ================================
@app.route("/shifts", methods=["POST"])
def create_shift():
    data = request.get_json()
    try:
        shift = Shift(
            employee_id=data["employee_id"],
            group_id=data["group_id"],
            date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
            start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
        )
        db.session.add(shift)
        db.session.commit()
        return jsonify({"message": "Shift created successfully", "id": shift.id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/shifts", methods=["GET"])
def list_shifts():
    shifts = Shift.query.all()
    result = [
        {
            "id": s.id,
            "employee_id": s.employee_id,
            "employee_name": s.employee.name if s.employee else None,
            "group_id": s.group_id,
            "group_name": s.group.name if s.group else None,
            "date": s.date.isoformat(),
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M")
        }
        for s in shifts
    ]
    return jsonify(result)


# ================================
# 🔹 シフト希望募集
# ================================
@app.route("/shift_requests", methods=["POST"])
@jwt_required()
def create_shift_request():
    claims = get_jwt()
    # グループ内で admin 権限を持つかチェック
    current_user_id = int(get_jwt_identity())
    
    data = request.get_json()
    group_id = data.get("group_id")
    
    # このユーザーがそのグループの管理者かチェック
    membership = GroupMembership.query.filter_by(
        user_id=current_user_id,
        group_id=group_id,
        role='admin'
    ).first()
    
    if not membership:
        return jsonify({"error": "Admin permission required for this group"}), 403

    title = data.get("title")
    description = data.get("description", "")

    if not group_id or not title:
        return jsonify({"error": "Missing required fields"}), 400

    if not Group.query.get(group_id):
        return jsonify({"error": f"Group {group_id} not found"}), 404

    new_request = ShiftRequest(
        group_id=group_id,
        title=title,
        description=description,
        created_by=current_user_id
    )
    db.session.add(new_request)
    db.session.commit()

    return jsonify({
        "message": "Shift request created successfully",
        "id": new_request.id
    }), 201


@app.route("/shift_requests", methods=["GET"])
@jwt_required()
def list_shift_requests():
    requests = ShiftRequest.query.order_by(ShiftRequest.created_at.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "group": r.group.name if r.group else None,
            "title": r.title,
            "description": r.description,
            "created_by": r.creator.email if r.creator else None,
            "created_at": r.created_at.isoformat()
        }
        for r in requests
    ]), 200


# ================================
# 🔹 その他のAPI（既存のまま）
# ================================
# 以下、shift_responses, my_shifts, wage_rates などの既存APIは省略
# app-fixed.py の該当部分をそのまま使用してください


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
