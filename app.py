from flask import Flask, render_template, request, redirect, url_for, jsonify, session as flask_session
import requests
import os
import json
from datetime import datetime, date
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "service_management_secure_production_key_2026"

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

TURSO_URL = "https://company-db-banktnt.aws-ap-northeast-1.turso.io/v2/pipeline"
TURSO_AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJleHAiOjE3ODkxNTE2NTAsImlhdCI6MTc4ODU0Njg1MCwiaWQiOiIwMWEwNmRiMC00MzAxLTdjYmYtYjkyNy1kZDQ3NTI2MDQyNWEiLCJraWQiOiJCWFFUVUtmVUlpc3BWUkFjdFdvWEVpY2pCVmlPcGFTZXBpLTk4QTA2b3Y0IiwicmlkIjoiOWUxYTlhNjUtMDNmNy00OWJiLWJhN2EtOWU2NTQxNTI4NjlmIn0.Z4EIk0YJlc5bJx-T-fXlr-nLedS0lVSer8g5UBjSfZEEl8yyhdpzpQuz1MN-BRRLdW8bStuAn3eqJVy-bstnDA"

http_session = requests.Session()
http_session.headers.update({
    "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
    "Content-Type": "application/json"
})

def query_turso(sql, args=None):
    stmt = {"sql": sql}
    if args:
        params = []
        for a in args:
            if a is None or a == "":
                params.append({"type": "null"})
            elif isinstance(a, int):
                params.append({"type": "integer", "value": str(a)})
            elif isinstance(a, float):
                params.append({"type": "float", "value": a})
            else:
                params.append({"type": "text", "value": str(a)})
        stmt["args"] = params

    payload = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
    try:
        res = http_session.post(TURSO_URL, json=payload, timeout=12)
        data = res.json()
        rows = []
        if "results" in data and len(data["results"]) > 0:
            resp = data["results"][0].get("response", {})
            if "error" in resp:
                print(f"Turso Error: {resp['error']}")
                return []
            for row in resp.get("result", {}).get("rows", []):
                rows.append([col.get("value") for col in row])
        return rows
    except Exception as e:
        print(f"Turso Error: {e}")
        return []

def ensure_db_schema():
    query_turso("ALTER TABLE products ADD COLUMN cost_price REAL DEFAULT 0")
    query_turso("ALTER TABLE products ADD COLUMN lot_no TEXT")
    query_turso("ALTER TABLE products ADD COLUMN received_date TEXT")
    query_turso("ALTER TABLE products ADD COLUMN expiry_date TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN work_result TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN photo_1 TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN photo_2 TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN photo_3 TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN signature_data TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN signed_by TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN completed_at TIMESTAMP")
    query_turso("ALTER TABLE jobs ADD COLUMN labor_fee REAL DEFAULT 0")
    query_turso("ALTER TABLE jobs ADD COLUMN spare_parts_fee REAL DEFAULT 0")
    query_turso("ALTER TABLE jobs ADD COLUMN travel_fee REAL DEFAULT 0")
    query_turso("ALTER TABLE jobs ADD COLUMN total_amount REAL DEFAULT 0")
    query_turso("ALTER TABLE jobs ADD COLUMN custom_customer_name TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN custom_customer_phone TEXT")
    query_turso("ALTER TABLE jobs ADD COLUMN assignment_remark TEXT")
    query_turso("ALTER TABLE users ADD COLUMN password TEXT DEFAULT '1234'")
    query_turso("""
        CREATE TABLE IF NOT EXISTS quotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_no TEXT UNIQUE,
            customer_id INTEGER,
            custom_company_name TEXT,
            custom_tax_id TEXT,
            custom_address TEXT,
            doc_date DATE,
            items_json TEXT,
            subtotal REAL,
            vat REAL,
            grand_total REAL,
            credit_term TEXT,
            delivery_term TEXT,
            validity_days TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def get_lang():
    return flask_session.get("lang", "th")

@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in ["th", "en"]:
        flask_session["lang"] = lang
    return redirect(request.referrer or url_for("index"))

TRANSLATIONS = {
    "th": {
        "title": "ระบบบันทึกและจัดการงานบริการ",
        "subtitle": "ระบบบริหารจัดการงานซ่อม สต็อก และใบเสนอราคาภาคสนาม",
        "menu_home": "งาน & สต็อก",
        "menu_quotation": "ใบเสนอราคา",
        "menu_tech": "ผู้ปฏิบัติงาน",
        "menu_admin": "ผู้ดูแลระบบ",
        "logout": "ออกจากระบบ",
        "login": "เข้าสู่ระบบ"
    },
    "en": {
        "title": "Service Management System",
        "subtitle": "Field Technical Service, Stock & Quotation Platform",
        "menu_home": "Jobs & Stock",
        "menu_quotation": "Quotation",
        "menu_tech": "Technician",
        "menu_admin": "Admin",
        "logout": "Logout",
        "login": "Login"
    }
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not flask_session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ==================== Authentication ====================

@app.route("/login", methods=["GET", "POST"])
def login():
    lang = get_lang()
    error = None
    if request.method == "POST":
        identifier = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        # ตรวจสอบล็อกอินรองรับเบอร์โทร, ชื่อผู้ใช้ หรือพิมพ์คำว่า admin
        user = query_turso("""
            SELECT id, full_name, role 
            FROM users 
            WHERE (phone = ? OR full_name = ? OR (role = 'admin' AND ? = 'admin')) 
              AND password = ?
        """, [identifier, identifier, identifier, password])

        if user:
            flask_session["user_id"] = user[0][0]
            flask_session["user_name"] = user[0][1]
            flask_session["user_role"] = user[0][2]

            if user[0][2] == "technician":
                return redirect(url_for("technician_portal"))
            return redirect(url_for("index"))
        else:
            error = "ไอดี/เบอร์โทร หรือ รหัสผ่านไม่ถูกต้อง (ช่าง: 1234, หัวหน้า: super555, แอดมิน: admin888)"
    return render_template("login.html", error=error, t=TRANSLATIONS[lang], lang=lang)

@app.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("login"))

# ==================== Dashboard & Jobs ====================

@app.route("/")
@login_required
def index():
    lang = get_lang()
    user_role = flask_session.get("user_role")
    if user_role == "technician":
        return redirect(url_for("technician_portal"))

    search_q = request.args.get("search_product", "").strip()
    customers_full = query_turso("SELECT id, company_name, tax_id, contact_person, phone, shipping_address, credit_terms FROM customers ORDER BY id DESC")

    if search_q:
        search_param = f"%{search_q}%"
        raw_products = query_turso("SELECT id, product_code, product_name, model, stock_qty, expiry_date FROM products WHERE product_name LIKE ? OR product_code LIKE ? OR model LIKE ? ORDER BY id DESC", [search_param, search_param, search_param])
    else:
        raw_products = query_turso("SELECT id, product_code, product_name, model, stock_qty, expiry_date FROM products ORDER BY id DESC")

    today = date.today()
    products_full = []
    expiring_count = 0
    expired_count = 0

    for p in raw_products:
        p_id = p[0]
        qty_val = int(p[4]) if p[4] is not None else 0
        p_dict = {
            "id": p_id, "product_code": p[1], "product_name": p[2], "model": p[3],
            "stock_qty": qty_val, "expiry_date": p[5], "expiry_status": "normal", "days_left": None, "usage_history": []
        }
        if p[5]:
            try:
                delta = (datetime.strptime(str(p[5]).strip()[:10], "%Y-%m-%d").date() - today).days
                p_dict["days_left"] = delta
                if delta < 0:
                    p_dict["expiry_status"] = "expired"; expired_count += 1
                elif delta <= 30:
                    p_dict["expiry_status"] = "warning"; expiring_count += 1
            except:
                pass

        history_rows = query_turso("""
            SELECT j.job_no, COALESCE(c.company_name, j.custom_customer_name), c.shipping_address, j.serial_no, j.created_at, u.full_name
            FROM jobs j LEFT JOIN customers c ON j.customer_id = c.id LEFT JOIN users u ON j.technician_id = u.id
            WHERE j.product_id = ? ORDER BY j.id DESC
        """, [p_id])
        for h in history_rows:
            p_dict["usage_history"].append({
                "job_no": h[0], "customer_name": h[1], "shipping_address": h[2],
                "serial_no": h[3], "created_at": h[4], "technician_name": h[5]
            })
        products_full.append(p_dict)

    technicians = query_turso("SELECT id, full_name FROM users WHERE role = 'technician'")
    supervisors = query_turso("SELECT id, full_name FROM users WHERE role = 'supervisor'")

    current_year = datetime.now().year
    count_data = query_turso("SELECT COUNT(*) FROM jobs")
    job_count = int(count_data[0][0]) if count_data and count_data[0][0] is not None else 0
    auto_job_no = f"JOB-{current_year}-{(job_count + 1):03d}"

    pending_approval_jobs = query_turso("""
        SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), j.serial_no, j.problem_detail, u.full_name, j.created_at, j.technician_id
        FROM jobs j
        LEFT JOIN customers c ON j.customer_id = c.id
        LEFT JOIN users u ON j.technician_id = u.id
        WHERE j.status = 'awaiting_approval'
        ORDER BY j.id DESC
    """)

    jobs = query_turso("""
        SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), p.product_name, u.full_name, j.status, j.problem_detail, j.serial_no, j.assignment_remark
        FROM jobs j 
        LEFT JOIN customers c ON j.customer_id = c.id 
        LEFT JOIN products p ON j.product_id = p.id 
        LEFT JOIN users u ON j.technician_id = u.id
        ORDER BY j.id DESC
    """)

    return render_template(
        "job_dashboard.html",
        customers=customers_full,
        products=products_full,
        technicians=technicians,
        supervisors=supervisors,
        pending_approval_jobs=pending_approval_jobs,
        jobs=jobs,
        auto_job_no=auto_job_no,
        expiring_count=expiring_count,
        expired_count=expired_count,
        search_q=search_q,
        t=TRANSLATIONS[lang],
        lang=lang,
        current_user=flask_session.get("user_name"),
        current_role=user_role
    )

@app.route("/customer/add", methods=["POST"])
@login_required
def add_customer():
    args = [request.form.get(k) for k in [
        "company_name", "tax_id", "branch_type", "branch_code", "contact_person",
        "contact_department", "phone", "email", "tax_address", "shipping_address", "credit_terms", "notes"
    ]]
    query_turso("INSERT INTO customers (company_name, tax_id, branch_type, branch_code, contact_person, contact_department, phone, email, tax_address, shipping_address, credit_terms, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", args)
    return redirect(url_for("index"))

@app.route("/product/add", methods=["POST"])
@login_required
def add_product():
    stock_qty = int(request.form.get("stock_qty", "0"))
    query_turso("INSERT INTO products (product_code, product_name, model, stock_qty, expiry_date) VALUES (?, ?, ?, ?, ?)", [
        request.form.get("product_code") or None, request.form.get("product_name"), request.form.get("model") or None, stock_qty, request.form.get("expiry_date") or None
    ])
    return redirect(url_for("index"))

@app.route("/job/create", methods=["POST"])
@login_required
def create_job():
    product_id = request.form.get("product_id")
    serial_no = request.form.get("serial_no") or "N/A"
    supervisor_name = flask_session.get("user_name")
    tech_id = request.form.get("technician_id")

    tech_info = query_turso("SELECT full_name FROM users WHERE id = ?", [tech_id])
    tech_name = tech_info[0][0] if tech_info else "ไม่ระบุ"
    remark = f"[อนุมัติ/สั่งการโดย: {supervisor_name} -> มอบหมายให้: {tech_name}]"

    query_turso("""
        INSERT INTO jobs (job_no, customer_id, product_id, serial_no, technician_id, supervisor_id, problem_detail, assignment_remark, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    """, [
        request.form.get("job_no"), request.form.get("customer_id"), product_id if product_id else None,
        serial_no, tech_id, flask_session.get("user_id"), request.form.get("problem_detail"), remark
    ])
    if product_id:
        query_turso("UPDATE products SET stock_qty = MAX(0, stock_qty - 1) WHERE id = ?", [product_id])
    return redirect(url_for("index"))

@app.route("/job/field-request", methods=["POST"])
@login_required
def field_request_job():
    user_id = flask_session.get("user_id")
    user_name = flask_session.get("user_name")
    current_year = datetime.now().year
    count_data = query_turso("SELECT COUNT(*) FROM jobs")
    job_count = int(count_data[0][0]) if count_data and count_data[0][0] is not None else 0
    auto_job_no = f"JOB-{current_year}-{(job_count + 1):03d}"

    mode = request.form.get("customer_mode", "master")
    customer_id = request.form.get("customer_id") if mode == "master" else None
    custom_name = request.form.get("custom_customer_name") if mode == "custom" else None
    custom_phone = request.form.get("custom_customer_phone") if mode == "custom" else None
    serial_no = request.form.get("serial_no") or "รอระบุ S/N"
    problem = request.form.get("problem_detail")
    remark = f"[แจ้งเปิดงานด่วนโดยช่าง: {user_name}]"

    query_turso("""
        INSERT INTO jobs (job_no, customer_id, custom_customer_name, custom_customer_phone, serial_no, technician_id, problem_detail, assignment_remark, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_approval')
    """, [auto_job_no, customer_id, custom_name, custom_phone, serial_no, user_id, problem, remark])

    return redirect(url_for("technician_portal"))

@app.route("/job/<int:job_id>/approve-assign", methods=["POST"])
@login_required
def approve_assign_job(job_id):
    supervisor_name = flask_session.get("user_name")
    assigned_tech_id = request.form.get("technician_id")
    tech_info = query_turso("SELECT full_name FROM users WHERE id = ?", [assigned_tech_id])
    tech_name = tech_info[0][0] if tech_info else "ช่างหน้างาน"

    existing_remark = query_turso("SELECT assignment_remark FROM jobs WHERE id = ?", [job_id])
    base_remark = existing_remark[0][0] if existing_remark and existing_remark[0][0] else ""
    new_remark = f"{base_remark} | [อนุมัติโดย: {supervisor_name} -> มอบหมายให้: {tech_name}]"

    query_turso("""
        UPDATE jobs 
        SET technician_id = ?, supervisor_id = ?, assignment_remark = ?, status = 'pending'
        WHERE id = ?
    """, [assigned_tech_id, flask_session.get("user_id"), new_remark, job_id])

    return redirect(request.referrer or url_for("index"))

@app.route("/api/customer-machines/<int:customer_id>")
@login_required
def customer_machines(customer_id):
    rows = query_turso("""
        SELECT DISTINCT p.product_name, j.serial_no, j.created_at 
        FROM jobs j LEFT JOIN products p ON j.product_id = p.id
        WHERE j.customer_id = ? AND j.serial_no IS NOT NULL AND j.serial_no != 'N/A'
        ORDER BY j.id DESC
    """, [customer_id])
    machines = [{"name": r[0] or "อุปกรณ์", "serial": r[1], "date": r[2]} for r in rows]
    return jsonify(machines)

# ==================== Quotations & Invoices ====================

@app.route("/invoice")
@app.route("/sales/invoice")
@login_required
def sales_invoice():
    lang = get_lang()
    user_role = flask_session.get("user_role")
    if user_role == "technician":
        return redirect(url_for("technician_portal"))

    edit_id = request.args.get("edit_id")
    customers = query_turso("SELECT id, company_name, tax_id, tax_address, phone, email, credit_terms FROM customers ORDER BY company_name ASC")
    quotations = query_turso("SELECT q.id, q.doc_no, COALESCE(c.company_name, q.custom_company_name), q.doc_date, q.grand_total, q.status FROM quotations q LEFT JOIN customers c ON q.customer_id = c.id ORDER BY q.id DESC")

    current_year = datetime.now().year
    count_qt = query_turso("SELECT COUNT(*) FROM quotations")
    qt_num = (int(count_qt[0][0]) + 1) if count_qt and count_qt[0][0] is not None else 1
    default_doc_no = f"QT-{current_year}-{qt_num:03d}"
    today_str = date.today().strftime("%Y-%m-%d")

    edit_data = None
    if edit_id:
        row = query_turso("""
            SELECT id, doc_no, customer_id, custom_company_name, custom_tax_id, custom_address,
                   doc_date, items_json, subtotal, vat, grand_total, credit_term, delivery_term, validity_days
            FROM quotations WHERE id = ?
        """, [edit_id])
        if row:
            r = row[0]
            edit_data = {
                "id": r[0], "doc_no": r[1], "customer_id": r[2], "custom_company_name": r[3] or "",
                "custom_tax_id": r[4] or "", "custom_address": r[5] or "", "doc_date": r[6],
                "items": json.loads(r[7]) if r[7] else [], "subtotal": r[8] or 0.0, "vat": r[9] or 0.0,
                "grand_total": r[10] or 0.0, "credit_term": r[11] or "โอนเงินสด / เครดิต 30 วัน",
                "delivery_term": r[12] or "3-7 วันทำการ", "validity_days": r[13] or "30 วัน"
            }

    return render_template(
        "invoice.html",
        customers=customers,
        quotations=quotations,
        default_doc_no=default_doc_no,
        today_str=today_str,
        edit_data=edit_data,
        t=TRANSLATIONS[lang],
        lang=lang,
        current_user=flask_session.get("user_name"),
        current_role=user_role
    )

@app.route("/invoice/save", methods=["POST"])
@login_required
def save_invoice():
    quotation_id = request.form.get("quotation_id")
    doc_no = request.form.get("doc_no")
    mode = request.form.get("customer_mode")
    customer_id = request.form.get("customer_id") if mode == "master" else None
    custom_company_name = request.form.get("custom_company_name")
    custom_tax_id = request.form.get("custom_tax_id")
    custom_address = request.form.get("custom_address")
    doc_date = request.form.get("doc_date") or date.today().strftime("%Y-%m-%d")
    credit_term = request.form.get("credit_term")
    delivery_term = request.form.get("delivery_term")
    validity_days = request.form.get("validity_days")

    item_names = request.form.getlist("item_name[]")
    item_qtys = request.form.getlist("item_qty[]")
    item_prices = request.form.getlist("item_price[]")

    items, subtotal = [], 0.0
    for name, qty, price in zip(item_names, item_qtys, item_prices):
        if name.strip():
            q, p = float(qty or 1), float(price or 0)
            tot = q * p
            subtotal += tot
            items.append({"name": name.strip(), "qty": q, "price": p, "total": tot})

    vat = round(subtotal * 0.07, 2)
    grand_total = round(subtotal + vat, 2)
    items_json = json.dumps(items, ensure_ascii=False)

    if quotation_id:
        query_turso("""
            UPDATE quotations 
            SET doc_no=?, customer_id=?, custom_company_name=?, custom_tax_id=?, custom_address=?,
                doc_date=?, items_json=?, subtotal=?, vat=?, grand_total=?, credit_term=?, delivery_term=?, validity_days=?
            WHERE id=?
        """, [doc_no, customer_id, custom_company_name, custom_tax_id, custom_address, doc_date, items_json, subtotal, vat, grand_total, credit_term, delivery_term, validity_days, quotation_id])
        target_id = quotation_id
    else:
        query_turso("""
            INSERT INTO quotations (doc_no, customer_id, custom_company_name, custom_tax_id, custom_address, doc_date, items_json, subtotal, vat, grand_total, credit_term, delivery_term, validity_days)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [doc_no, customer_id, custom_company_name, custom_tax_id, custom_address, doc_date, items_json, subtotal, vat, grand_total, credit_term, delivery_term, validity_days])
        saved = query_turso("SELECT id FROM quotations WHERE doc_no = ?", [doc_no])
        target_id = saved[0][0] if saved else None

    return redirect(url_for("sales_invoice", edit_id=target_id)) if target_id else redirect(url_for("sales_invoice"))

@app.route("/invoice/delete/<int:id>", methods=["POST"])
@login_required
def delete_invoice(id):
    query_turso("DELETE FROM quotations WHERE id = ?", [id])
    return redirect(url_for("sales_invoice"))

# ==================== User Management (Admin / Supervisor) ====================

@app.route("/admin/users")
@login_required
def admin_users():
    lang = get_lang()
    user_role = flask_session.get("user_role")
    if user_role not in ["admin", "supervisor"]:
        return redirect(url_for("technician_portal"))

    users = query_turso("SELECT id, full_name, role, phone, password, created_at FROM users ORDER BY id DESC")
    return render_template("admin_users.html", users=users, t=TRANSLATIONS[lang], lang=lang, current_user=flask_session.get("user_name"), current_role=user_role)

@app.route("/user/add", methods=["POST"])
@login_required
def add_user():
    role = request.form.get("role")
    default_pass = "admin888" if role == "admin" else ("super555" if role == "supervisor" else "1234")
    password = request.form.get("password") or default_pass

    args = [
        request.form.get("full_name"),
        role,
        request.form.get("phone"),
        password
    ]
    query_turso("INSERT INTO users (full_name, role, phone, password) VALUES (?, ?, ?, ?)", args)
    return redirect(url_for("admin_users"))

# ==================== Technician Portal ====================

@app.route("/technician")
@login_required
def technician_portal():
    lang = get_lang()
    user_id = flask_session.get("user_id")
    user_role = flask_session.get("user_role")

    customers = query_turso("SELECT id, company_name FROM customers ORDER BY company_name ASC")
    technicians = []

    if user_role in ["admin", "supervisor"]:
        technicians = query_turso("SELECT id, full_name, role FROM users WHERE role = 'technician'")
        selected_tech_id = request.args.get("tech_id") or user_id
    else:
        selected_tech_id = user_id

    jobs = []
    selected_tech_name = flask_session.get("user_name")

    if user_role in ["admin", "supervisor"] and not request.args.get("tech_id"):
        jobs = query_turso("""
            SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), c.contact_person, c.phone, c.shipping_address, 
                   p.product_name, j.serial_no, j.problem_detail, j.status, j.created_at, u.full_name, j.assignment_remark
            FROM jobs j
            LEFT JOIN customers c ON j.customer_id = c.id
            LEFT JOIN products p ON j.product_id = p.id
            LEFT JOIN users u ON j.technician_id = u.id
            WHERE j.status != 'awaiting_approval'
            ORDER BY CASE WHEN j.status = 'pending' THEN 1 ELSE 2 END, j.id DESC
        """)
    else:
        jobs = query_turso("""
            SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), c.contact_person, c.phone, c.shipping_address, 
                   p.product_name, j.serial_no, j.problem_detail, j.status, j.created_at, u.full_name, j.assignment_remark
            FROM jobs j
            LEFT JOIN customers c ON j.customer_id = c.id
            LEFT JOIN products p ON j.product_id = p.id
            LEFT JOIN users u ON j.technician_id = u.id
            WHERE j.technician_id = ? AND j.status != 'awaiting_approval'
            ORDER BY CASE WHEN j.status = 'pending' THEN 1 ELSE 2 END, j.id DESC
        """, [selected_tech_id])

    pending_approval_jobs = []
    if user_role in ["admin", "supervisor"]:
        pending_approval_jobs = query_turso("""
            SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), j.serial_no, j.problem_detail, u.full_name, j.created_at, j.custom_customer_phone, j.technician_id
            FROM jobs j
            LEFT JOIN customers c ON j.customer_id = c.id
            LEFT JOIN users u ON j.technician_id = u.id
            WHERE j.status = 'awaiting_approval'
            ORDER BY j.id DESC
        """)

    return render_template(
        "technician_dashboard.html",
        technicians=technicians,
        customers=customers,
        jobs=jobs,
        pending_approval_jobs=pending_approval_jobs,
        selected_tech_id=selected_tech_id,
        selected_tech_name=selected_tech_name,
        user_role=user_role,
        t=TRANSLATIONS[lang],
        lang=lang,
        current_user=flask_session.get("user_name"),
        current_role=user_role
    )

@app.route("/technician/job/<int:job_id>")
@login_required
def technician_job_detail(job_id):
    lang = get_lang()
    user_role = flask_session.get("user_role")
    job_data = query_turso("""
        SELECT j.id, j.job_no, COALESCE(c.company_name, j.custom_customer_name), c.contact_person, 
               COALESCE(c.phone, j.custom_customer_phone), c.shipping_address,
               p.product_name, p.model, j.serial_no, j.problem_detail, j.status,
               j.work_result, j.photo_1, j.photo_2, j.photo_3, j.signature_data, j.signed_by, j.technician_id,
               j.created_at, j.completed_at, u.full_name, c.tax_id,
               COALESCE(j.labor_fee, 0), COALESCE(j.spare_parts_fee, 0), COALESCE(j.travel_fee, 0), COALESCE(j.total_amount, 0),
               j.assignment_remark
        FROM jobs j
        LEFT JOIN customers c ON j.customer_id = c.id
        LEFT JOIN products p ON j.product_id = p.id
        LEFT JOIN users u ON j.technician_id = u.id
        WHERE j.id = ?
    """, [job_id])

    if not job_data:
        return redirect(url_for("technician_portal"))

    j = job_data[0]
    job = {
        "id": j[0], "job_no": j[1], "customer_name": j[2], "contact_person": j[3], "phone": j[4],
        "shipping_address": j[5], "product_name": j[6], "model": j[7], "serial_no": j[8],
        "problem_detail": j[9], "status": j[10], "work_result": j[11], "photo_1": j[12],
        "photo_2": j[13], "photo_3": j[14], "signature_data": j[15], "signed_by": j[16],
        "technician_id": j[17], "created_at": j[18], "completed_at": j[19], "technician_name": j[20],
        "customer_tax_id": j[21],
        "labor_fee": float(j[22]), "spare_parts_fee": float(j[23]), "travel_fee": float(j[24]), "total_amount": float(j[25]),
        "assignment_remark": j[26]
    }
    return render_template("technician_job.html", job=job, t=TRANSLATIONS[lang], lang=lang, current_user=flask_session.get("user_name"), current_role=user_role)

@app.route("/technician/job/<int:job_id>/save-draft", methods=["POST"])
@login_required
def technician_save_draft(job_id):
    work_result = request.form.get("work_result")
    serial_no = request.form.get("serial_no")
    labor_fee = float(request.form.get("labor_fee") or 0)
    spare_parts_fee = float(request.form.get("spare_parts_fee") or 0)
    travel_fee = float(request.form.get("travel_fee") or 0)
    total_amount = labor_fee + spare_parts_fee + travel_fee

    photos = [None, None, None]
    for idx, field in enumerate(["photo_1", "photo_2", "photo_3"]):
        file = request.files.get(field)
        if file and file.filename != "":
            filename = f"job_{job_id}_{idx+1}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            photos[idx] = f"/static/uploads/{filename}"

    existing = query_turso("SELECT photo_1, photo_2, photo_3 FROM jobs WHERE id = ?", [job_id])
    if existing:
        for i in range(3):
            if not photos[i]:
                photos[i] = existing[0][i]

    query_turso("""
        UPDATE jobs 
        SET work_result = ?, serial_no = ?, labor_fee = ?, spare_parts_fee = ?, travel_fee = ?, total_amount = ?,
            photo_1 = ?, photo_2 = ?, photo_3 = ?
        WHERE id = ?
    """, [work_result, serial_no, labor_fee, spare_parts_fee, travel_fee, total_amount, photos[0], photos[1], photos[2], job_id])

    return redirect(url_for("technician_job_detail", job_id=job_id, step="sign"))

@app.route("/technician/job/<int:job_id>/close", methods=["POST"])
@login_required
def technician_close_job(job_id):
    signed_by = request.form.get("signed_by")
    signature_data = request.form.get("signature_data")
    tech_id = request.form.get("technician_id")

    query_turso("""
        UPDATE jobs 
        SET signature_data = ?, signed_by = ?, status = 'completed', completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, [signature_data, signed_by, job_id])

    return redirect(url_for("technician_portal", tech_id=tech_id))

if __name__ == "__main__":
    ensure_db_schema()
    app.run(debug=True, port=5000)