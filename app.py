from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS  # ← 追加
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import traceback
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt
)

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
# 🔹 モデル
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
    description = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class GroupMembership(db.Model):
    __tablename__ = 'group_memberships'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    joined_at = db.Column(db.DateTime, server_default=db.func.now())

    employee = db.relationship('Employee', backref='memberships', lazy=True)
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
    role = db.Column(db.String(50), default="teacher")

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
# 🔹 ルート
# ================================
@app.route("/")
def home():
    return jsonify({"message": "✅ Flask backend is running successfully!"})


# Employee CRUD
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


# Group CRUD
@app.route("/groups", methods=["GET"])
def get_groups():
    groups = Group.query.all()
    return jsonify([
        {"id": g.id, "name": g.name, "description": g.description}
        for g in groups
    ])


@app.route("/groups", methods=["POST"])
def create_group():
    data = request.get_json()
    if not data.get("name"):
        return jsonify({"error": "Group name is required"}), 400
    group = Group(**data)
    db.session.add(group)
    db.session.commit()
    return jsonify({"message": "Group created successfully"}), 201


# Group Membership
@app.route("/group_memberships", methods=["POST"])
def add_employee_to_group():
    data = request.get_json()
    if not data.get("employee_id") or not data.get("group_id"):
        return jsonify({"error": "employee_id and group_id are required"}), 400
    membership = GroupMembership(**data)
    db.session.add(membership)
    db.session.commit()
    return jsonify({"message": "Employee added to group successfully"}), 201


# Shift
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


# 🔐 Auth
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email, password, role = data.get("email"), data.get("password"), data.get("role", "teacher")
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400
    user = User(email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User registered"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email, password = data.get("email"), data.get("password")
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"email": user.email, "role": user.role}
    )
    return jsonify({"access_token": token}), 200


# 📅 シフト希望募集
@app.route("/shift_requests", methods=["POST"])
@jwt_required()
def create_shift_request():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json()
    group_id = data.get("group_id")
    title = data.get("title")
    description = data.get("description", "")

    if not group_id or not title:
        return jsonify({"error": "Missing required fields"}), 400

    if not Group.query.get(group_id):
        return jsonify({"error": f"Group {group_id} not found"}), 404

    creator_id = int(get_jwt_identity())

    new_request = ShiftRequest(
        group_id=group_id,
        title=title,
        description=description,
        created_by=creator_id
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


# 🧑‍🏫 講師の希望回答
@app.route("/shift_responses", methods=["POST"])
@jwt_required()
def create_shift_response():
    data = request.get_json()

    try:
        current_user_id = int(get_jwt_identity())
    except Exception:
        return jsonify({"error": "Invalid user identity in token"}), 400

    request_id = data.get("request_id")
    comment = data.get("comment", "")

    preferred_date = None
    preferred_start = None
    preferred_end = None
    try:
        if data.get("preferred_date"):
            preferred_date = datetime.strptime(data["preferred_date"], "%Y-%m-%d").date()
        if data.get("preferred_start"):
            preferred_start = datetime.strptime(data["preferred_start"], "%H:%M").time()
        if data.get("preferred_end"):
            preferred_end = datetime.strptime(data["preferred_end"], "%H:%M").time()
    except ValueError:
        return jsonify({"error": "Invalid date/time format"}), 400

    if not request_id:
        return jsonify({"error": "request_id is required"}), 400

    if not ShiftRequest.query.get(request_id):
        return jsonify({"error": f"ShiftRequest {request_id} not found"}), 404

    claims = get_jwt()
    user_email = claims.get("email")
    employee = None
    if user_email:
        employee = Employee.query.filter_by(email=user_email).first()

    if not employee:
        auto_code = f"user-{current_user_id}"
        employee_name = user_email.split('@')[0] if user_email else f"user_{current_user_id}"
        employee = Employee(employee_code=auto_code, name=employee_name, email=user_email)
        try:
            db.session.add(employee)
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Failed to create linked Employee record"}), 500

    response = ShiftResponse(
        request_id=request_id,
        employee_id=employee.id,
        preferred_date=preferred_date,
        preferred_start=preferred_start,
        preferred_end=preferred_end,
        comment=comment
    )
    try:
        db.session.add(response)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": "Shift response submitted",
        "id": response.id
    }), 201


@app.route("/shift_responses", methods=["GET"])
@jwt_required()
def list_shift_responses():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    responses = ShiftResponse.query.all()
    result = [
        {
            "id": r.id,
            "request": r.request.title,
            "employee": r.employee.name,
            "date": r.preferred_date.isoformat() if r.preferred_date else None,
            "time": f"{r.preferred_start.strftime('%H:%M')} ~ {r.preferred_end.strftime('%H:%M')}" if r.preferred_start and r.preferred_end else None,
            "comment": r.comment
        }
        for r in responses
    ]
    return jsonify(result)


@app.route("/shift_responses/<int:response_id>/approve", methods=["POST"])
@jwt_required()
def approve_shift_response(response_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    response = ShiftResponse.query.get(response_id)
    if not response:
        return jsonify({"error": "Shift response not found"}), 404

    request_info = response.request
    employee_id = response.employee_id
    date = response.preferred_date
    start_time = response.preferred_start
    end_time = response.preferred_end

    if not (date and start_time and end_time):
        return jsonify({"error": "Response does not contain preferred date/time"}), 400

    conflict = Shift.query.filter_by(
        employee_id=employee_id,
        date=date,
        start_time=start_time,
        end_time=end_time
    ).first()

    if conflict:
        return jsonify({"error": "Shift already exists for this time"}), 400

    new_shift = Shift(
        employee_id=employee_id,
        group_id=request_info.group_id,
        date=date,
        start_time=start_time,
        end_time=end_time
    )
    try:
        db.session.add(new_shift)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": "Shift approved and registered",
        "shift_id": new_shift.id,
        "employee_id": employee_id
    }), 201


@app.route("/my_shifts", methods=["GET"])
@jwt_required()
def get_my_shifts():
    try:
        token_id = int(get_jwt_identity())
    except Exception:
        return jsonify({"error": "Invalid token identity"}), 400

    employee = Employee.query.get(token_id)
    if not employee:
        claims = get_jwt()
        email = claims.get("email")
        if email:
            employee = Employee.query.filter_by(email=email).first()

    if not employee:
        return jsonify([])

    shifts = Shift.query.filter_by(employee_id=employee.id).order_by(Shift.date.asc()).all()
    result = [
        {
            "date": s.date.isoformat(),
            "group": s.group.name if s.group else None,
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
        }
        for s in shifts
    ]
    return jsonify(result)


# 💰 WageRate API
@app.route("/wage_rates", methods=["POST"])
@jwt_required()
def create_wage_rate():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json()
    group_id = data.get("group_id")
    hourly_rate = data.get("hourly_rate")
    note = data.get("note", "")
    effective_from = data.get("effective_from")

    if not (group_id and hourly_rate and effective_from):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        effective_from_date = datetime.strptime(effective_from, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    if not Group.query.get(group_id):
        return jsonify({"error": f"group_id {group_id} not found"}), 404

    wage = WageRate(
        group_id=group_id,
        hourly_rate=hourly_rate,
        effective_from=effective_from_date,
        note=note
    )
    db.session.add(wage)
    db.session.commit()
    return jsonify({"message": "Wage rate created successfully", "id": wage.id}), 201


@app.route("/wage_rates", methods=["GET"])
@jwt_required()
def list_wage_rates():
    rates = WageRate.query.order_by(WageRate.effective_from.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "group": r.group.name if r.group else None,
            "hourly_rate": r.hourly_rate,
            "effective_from": r.effective_from.isoformat(),
            "note": r.note
        }
        for r in rates
    ])


@app.route("/salary_estimate/<int:employee_id>", methods=["GET"])
@jwt_required()
def salary_estimate(employee_id):
    month_str = request.args.get("month")
    if not month_str:
        return jsonify({"error": "month parameter required (YYYY-MM)"}), 400

    try:
        target_month = datetime.strptime(month_str, "%Y-%m")
    except ValueError:
        return jsonify({"error": "Invalid month format (YYYY-MM)"}), 400

    start_date = target_month.replace(day=1)
    if start_date.month == 12:
        end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)

    shifts = Shift.query.filter(
        Shift.employee_id == employee_id,
        Shift.date >= start_date,
        Shift.date <= end_date
    ).all()

    if not shifts:
        return jsonify({"message": "No shifts found for this month"}), 200

    total_hours = 0.0
    total_salary = 0.0

    for s in shifts:
        duration = (datetime.combine(datetime.min, s.end_time) -
                    datetime.combine(datetime.min, s.start_time)).total_seconds() / 3600

        wage = WageRate.query.filter(
            WageRate.group_id == s.group_id,
            WageRate.effective_from <= s.date
        ).order_by(WageRate.effective_from.desc()).first()

        hourly_rate = wage.hourly_rate if wage else 0
        total_hours += duration
        total_salary += duration * hourly_rate

    return jsonify({
        "employee_id": employee_id,
        "month": month_str,
        "total_hours": round(total_hours, 2),
        "estimated_salary": round(total_salary, 0)
    }), 200


# 🔄 Shift Swap
@app.route("/shift_swaps", methods=["POST"])
@jwt_required()
def create_shift_swap():
    claims = get_jwt()
    current_user_id = int(get_jwt_identity())

    if claims.get("role") != "teacher":
        return jsonify({"error": "Only teachers can request swaps"}), 403

    data = request.get_json()
    shift_id = data.get("shift_id")
    reason = data.get("reason", "")

    if not shift_id:
        return jsonify({"error": "shift_id is required"}), 400

    shift = Shift.query.get(shift_id)
    if not shift:
        return jsonify({"error": f"Shift {shift_id} not found"}), 404

    if shift.employee_id != current_user_id:
        return jsonify({"error": "You can only request swaps for your own shifts"}), 403

    swap = ShiftSwap(
        shift_id=shift_id,
        requester_id=current_user_id,
        reason=reason,
        status="pending"
    )
    db.session.add(swap)
    db.session.commit()

    return jsonify({
        "message": "Shift swap requested successfully",
        "id": swap.id,
        "status": swap.status
    }), 201


@app.route("/shift_swaps", methods=["GET"])
@jwt_required()
def list_shift_swaps():
    swaps = ShiftSwap.query.order_by(ShiftSwap.created_at.desc()).all()
    result = [
        {
            "id": s.id,
            "shift_id": s.shift_id,
            "requester": s.requester.name if s.requester else None,
            "group": s.shift.group.name if s.shift and s.shift.group else None,
            "date": s.shift.date.isoformat() if s.shift else None,
            "time": f"{s.shift.start_time.strftime('%H:%M')}~{s.shift.end_time.strftime('%H:%M')}" if s.shift else None,
            "reason": s.reason,
            "status": s.status
        }
        for s in swaps
    ]
    return jsonify(result)


@app.route("/shift_swaps/<int:swap_id>", methods=["PATCH"])
@jwt_required()
def update_shift_swap_status(swap_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    data = request.get_json()
    new_status = data.get("status")
    new_employee_id = data.get("new_employee_id")

    if new_status not in ["approved", "rejected"]:
        return jsonify({"error": "Invalid status"}), 400

    swap = ShiftSwap.query.get(swap_id)
    if not swap:
        return jsonify({"error": "Shift swap not found"}), 404

    swap.status = new_status

    if new_status == "approved":
        if not new_employee_id:
            return jsonify({"error": "new_employee_id is required for approval"}), 400

        new_employee = Employee.query.get(new_employee_id)
        if not new_employee:
            return jsonify({"error": f"Employee {new_employee_id} not found"}), 404

        shift = swap.shift
        old_employee_id = shift.employee_id
        shift.employee_id = new_employee_id

        history = ShiftHistory(
            shift_id=shift.id,
            old_employee_id=old_employee_id,
            new_employee_id=new_employee_id,
            changed_by=claims.get("email")
        )
        db.session.add(history)

    db.session.commit()

    return jsonify({
        "message": f"Shift swap {new_status}",
        "swap_id": swap.id,
        "status": swap.status
    }), 200


# 🗂️ 管理者用
@app.route("/admin/shift_overview", methods=["GET"])
@jwt_required()
def admin_shift_overview():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"error": "Admin only"}), 403

    shifts = Shift.query.all()
    result = []

    for s in shifts:
        history = ShiftHistory.query.filter_by(shift_id=s.id).order_by(ShiftHistory.changed_at.desc()).first()
        result.append({
            "shift_id": s.id,
            "group": s.group.name if s.group else None,
            "current_employee": s.employee.name if s.employee else None,
            "date": s.date.isoformat(),
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "last_changed": history.changed_at.isoformat() if history else None,
            "changed_by": history.changed_by if history else None
        })

    return jsonify(result)


@app.route("/shift_histories", methods=["GET"])
@jwt_required()
def list_shift_histories():
    histories = ShiftHistory.query.order_by(ShiftHistory.changed_at.desc()).all()
    result = [
        {
            "id": h.id,
            "shift_id": h.shift_id,
            "old_employee": h.old_employee.name if h.old_employee else None,
            "new_employee": h.new_employee.name if h.new_employee else None,
            "changed_by": h.changed_by,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None
        }
        for h in histories
    ]
    return jsonify(result)


@app.route("/i18n/message", methods=["POST"])
def get_translated_message():
    data = request.get_json()
    key = data.get("key")
    lang = data.get("lang", "ja")

    translations = {
        "shift_created": {
            "ja": "シフトが作成されました。",
            "en": "Shift created successfully.",
            "zh": "班表已成功建立。"
        },
        "error_not_found": {
            "ja": "対象データが見つかりません。",
            "en": "Target data not found.",
            "zh": "找不到目标数据。"
        },
        "approved": {
            "ja": "承認されました。",
            "en": "Approved.",
            "zh": "已批准。"
        }
    }

    if key not in translations:
        return jsonify({"error": "Invalid key"}), 400

    message = translations[key].get(lang, translations[key]["ja"])
    return jsonify({"message": message})


# Global exception handler
@app.errorhandler(Exception)
def handle_exception(e):
    tb = traceback.format_exc()
    try:
        with open('error_debug.log', 'a', encoding='utf-8') as f:
            f.write(tb + '\n')
    except Exception:
        pass
    return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
