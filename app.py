import sqlite3
import datetime
import os
from flask import Flask, render_template, request, redirect, url_for, flash # type: ignore
from werkzeug.utils import secure_filename # type: ignore

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # change in production

# Configuration for file uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

from werkzeug.utils import secure_filename
import os

# Inside POST block
photo = member['photo'] if request.method == 'POST' and member else None  # for edit
if 'photo' in request.files:
    file = request.files['photo']
    if file and file.filename:
        if not allowed_file(file.filename):
            flash('Invalid file type. Allowed: png, jpg, jpeg, gif', 'warning')
        else:
            try:
                filename = secure_filename(file.filename)
                # Add timestamp to avoid collisions
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"member_{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo = filename
            except Exception as e:
                flash(f'Error saving photo: {str(e)}', 'danger')

DB_NAME = "church_attendance.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist, and add photo column if missing."""
    conn = get_db_connection()
    cur = conn.cursor()
    # Members table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            joined_date TEXT DEFAULT CURRENT_DATE
        )
    ''')
    # Services table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            service_date TEXT NOT NULL,
            service_time TEXT,
            notes TEXT
        )
    ''')
    # Attendance table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Present', 'Absent')),
            checkin_time TEXT,
            FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE,
            FOREIGN KEY (service_id) REFERENCES services (id) ON DELETE CASCADE,
            UNIQUE(member_id, service_id)
        )
    ''')
    # Add photo column to members if not exists (for older databases)
    cur.execute("PRAGMA table_info(members)")
    columns = [col[1] for col in cur.fetchall()]
    if 'photo' not in columns:
        cur.execute("ALTER TABLE members ADD COLUMN photo TEXT")
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== Routes ====================

@app.route('/')
def index():
    """Dashboard with statistics."""
    conn = get_db_connection()
    # Basic counts
    member_count = conn.execute('SELECT COUNT(*) FROM members').fetchone()[0]
    service_count = conn.execute('SELECT COUNT(*) FROM services').fetchone()[0]
    
    # Overall attendance percentage
    total_attendance = conn.execute('SELECT COUNT(*) FROM attendance').fetchone()[0]
    present_count = conn.execute("SELECT COUNT(*) FROM attendance WHERE status='Present'").fetchone()[0]
    overall_pct = (present_count / total_attendance * 100) if total_attendance > 0 else 0
    
    # Last 5 services with attendance counts
    recent_services = conn.execute('''
        SELECT s.id, s.service_name, s.service_date,
               COUNT(a.id) as total,
               SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END) as present
        FROM services s
        LEFT JOIN attendance a ON s.id = a.service_id
        GROUP BY s.id
        ORDER BY s.service_date DESC, s.service_time DESC
        LIMIT 5
    ''').fetchall()
    
    # For chart: labels and data from recent_services (reverse to show chronological order)
    chart_labels = [f"{row['service_date']} {row['service_name'][:15]}" for row in recent_services][::-1]
    chart_data = [row['present'] for row in recent_services][::-1]
    
    conn.close()
    return render_template('index.html',
                           member_count=member_count,
                           service_count=service_count,
                           overall_pct=round(overall_pct, 1),
                           recent_services=recent_services,
                           chart_labels=chart_labels,
                           chart_data=chart_data)

# ---------- Member Management ----------
@app.route('/members')
def list_members():
    conn = get_db_connection()
    members = conn.execute('SELECT * FROM members ORDER BY name').fetchall()
    conn.close()
    return render_template('members.html', members=members)

@app.route('/members/add', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        name = request.form['name'].strip()
        if not name:
            flash('Name is required.', 'danger')
            return redirect(url_for('add_member'))
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        
        # Handle file upload
        photo = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                # Generate safe filename and save
                filename = secure_filename(file.filename)
                # Add timestamp to avoid collisions
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"member_{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo = filename
            elif file and file.filename:
                flash('Invalid file type. Allowed: png, jpg, jpeg, gif', 'warning')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO members (name, phone, email, address, photo)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, phone, email, address, photo))
        conn.commit()
        conn.close()
        flash('Member added successfully.', 'success')
        return redirect(url_for('list_members'))
    return render_template('member_form.html')

@app.route('/members/edit/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    conn = get_db_connection()
    member = conn.execute('SELECT * FROM members WHERE id = ?', (member_id,)).fetchone()
    if not member:
        flash('Member not found.', 'danger')
        return redirect(url_for('list_members'))
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        if not name:
            flash('Name is required.', 'danger')
            return redirect(url_for('edit_member', member_id=member_id))
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        
        # Handle photo upload
        photo = member['photo']  # keep old by default
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                # Delete old photo if exists
                if photo:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], photo)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                # Save new photo
                filename = secure_filename(file.filename)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"member_{timestamp}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo = filename
            elif file and file.filename:
                flash('Invalid file type. Allowed: png, jpg, jpeg, gif', 'warning')
        
        conn.execute('''
            UPDATE members SET name = ?, phone = ?, email = ?, address = ?, photo = ?
            WHERE id = ?
        ''', (name, phone, email, address, photo, member_id))
        conn.commit()
        conn.close()
        flash('Member updated successfully.', 'success')
        return redirect(url_for('list_members'))
    
    conn.close()
    return render_template('member_form.html', member=member)

@app.route('/members/delete/<int:member_id>', methods=['POST'])
def delete_member(member_id):
    conn = get_db_connection()
    # Get photo filename before deleting record
    member = conn.execute('SELECT photo FROM members WHERE id = ?', (member_id,)).fetchone()
    if member and member['photo']:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], member['photo'])
        if os.path.exists(photo_path):
            os.remove(photo_path)
    conn.execute('DELETE FROM members WHERE id = ?', (member_id,))
    conn.commit()
    conn.close()
    flash('Member deleted.', 'success')
    return redirect(url_for('list_members'))

# ---------- Service Management ----------
@app.route('/services')
def list_services():
    conn = get_db_connection()
    services = conn.execute('SELECT * FROM services ORDER BY service_date DESC, service_time').fetchall()
    conn.close()
    return render_template('services.html', services=services)

@app.route('/services/add', methods=['GET', 'POST'])
def add_service():
    if request.method == 'POST':
        name = request.form['service_name'].strip()
        if not name:
            flash('Service name is required.', 'danger')
            return redirect(url_for('add_service'))
        date_str = request.form.get('service_date', datetime.date.today().isoformat())
        time_str = request.form.get('service_time', '').strip()
        notes = request.form.get('notes', '').strip()
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO services (service_name, service_date, service_time, notes)
            VALUES (?, ?, ?, ?)
        ''', (name, date_str, time_str, notes))
        conn.commit()
        conn.close()
        flash('Service added successfully.', 'success')
        return redirect(url_for('list_services'))
    today = datetime.date.today().isoformat()
    return render_template('service_form.html', today=today)

# ---------- Attendance ----------
@app.route('/attendance/record', methods=['GET', 'POST'])
def record_attendance():
    conn = get_db_connection()
    if request.method == 'POST':
        service_id = request.form.get('service_id')
        if not service_id:
            flash('No service selected.', 'danger')
            return redirect(url_for('record_attendance'))
        now = datetime.datetime.now().isoformat()
        present_ids = request.form.getlist('member_ids')
        members = conn.execute('SELECT id FROM members').fetchall()
        for member in members:
            mid = str(member['id'])
            status = 'Present' if mid in present_ids else 'Absent'
            conn.execute('''
                INSERT OR REPLACE INTO attendance (member_id, service_id, status, checkin_time)
                VALUES (?, ?, ?, ?)
            ''', (mid, service_id, status, now))
        conn.commit()
        flash('Attendance recorded successfully.', 'success')
        conn.close()
        return redirect(url_for('view_service_attendance', service_id=service_id))
    
    services = conn.execute('SELECT * FROM services ORDER BY service_date DESC, service_time').fetchall()
    members = conn.execute('SELECT id, name FROM members ORDER BY name').fetchall()
    conn.close()
    return render_template('record_attendance.html', services=services, members=members)

@app.route('/attendance/service/<int:service_id>')
def view_service_attendance(service_id):
    conn = get_db_connection()
    service = conn.execute('SELECT * FROM services WHERE id = ?', (service_id,)).fetchone()
    if not service:
        flash('Service not found.', 'danger')
        return redirect(url_for('list_services'))
    attendance = conn.execute('''
        SELECT m.name, a.status, a.checkin_time
        FROM attendance a
        JOIN members m ON a.member_id = m.id
        WHERE a.service_id = ?
        ORDER BY m.name
    ''', (service_id,)).fetchall()
    present_count = sum(1 for a in attendance if a['status'] == 'Present')
    total = len(attendance)
    conn.close()
    return render_template('view_attendance.html',
                           service=service,
                           attendance=attendance,
                           present_count=present_count,
                           total=total)

@app.route('/attendance/member/<int:member_id>')
def view_member_attendance(member_id):
    conn = get_db_connection()
    member = conn.execute('SELECT name, photo FROM members WHERE id = ?', (member_id,)).fetchone()
    if not member:
        flash('Member not found.', 'danger')
        return redirect(url_for('list_members'))
    history = conn.execute('''
        SELECT s.service_date, s.service_name, a.status
        FROM attendance a
        JOIN services s ON a.service_id = s.id
        WHERE a.member_id = ?
        ORDER BY s.service_date DESC, s.service_time
    ''', (member_id,)).fetchall()
    present_count = sum(1 for h in history if h['status'] == 'Present')
    total = len(history)
    conn.close()
    return render_template('member_history.html',
                           member=member,
                           history=history,
                           present_count=present_count,
                           total=total)

if __name__ == '__main__':
    app.run(debug=True)