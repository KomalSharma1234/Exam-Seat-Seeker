from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from fpdf import FPDF
from nlp_processor import process_pdf 
from thefuzz import process, fuzz
global_nlp_data = []
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'
CAMPUS_BLOCKS = {
    "EDISON": [30.5165, 76.6600],
    "NEWTON": [30.5170, 76.6590],
    "ARMSTRONG": [30.5155, 76.6585],
    "GALILEO": [30.5160, 76.6595],
    "EINSTEIN": [30.5158, 76.6592],
    "TURING": [30.5169, 76.6590],
    "PASCAL": [30.5152, 76.6582],
    "DEMORGAN": [30.51685, 76.6591],
}

def get_block_coords(block_name):
    if not block_name: return [30.5161, 76.6592] 
    for b_key, coords in CAMPUS_BLOCKS.items():
        if b_key in block_name.upper():
            return coords
    return [30.5161, 76.6592]
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///examseat_v5.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  
db = SQLAlchemy(app)
with app.app_context():
    db.create_all()
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') 
    admit_card_file = db.Column(db.String(200), nullable=True)
class Center(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    seats = db.relationship('Seat', backref='center', lazy=True)
class Seat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    center_id = db.Column(db.Integer, db.ForeignKey('center.id'), nullable=False)
    seat_number = db.Column(db.String(50), nullable=False)
    is_available = db.Column(db.Boolean, default=True)

class TeacherDuty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(100), nullable=True)
    exam_name = db.Column(db.String(100), nullable=True)
    block = db.Column(db.String(100), nullable=True)
    date = db.Column(db.String(50), nullable=True)
    time = db.Column(db.String(50), nullable=True)

class StudentSeating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=True, default="N/A")
    block = db.Column(db.String(100), nullable=True)
    row = db.Column(db.String(50), nullable=True)
    seat = db.Column(db.String(50), nullable=True)
    exam_date = db.Column(db.String(50), nullable=True)
    time = db.Column(db.String(50), nullable=True)
def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None
@app.route('/')
def home():
    user = get_current_user()
    if user:
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))
    return render_template('index.html', user=None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = 'student'

        if not username:
            flash('Username is required.', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'error')
            return redirect(url_for('register'))

        pwd_hash = generate_password_hash(password)
        new_user = User(username=username, password_hash=pwd_hash, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('home'))
    return render_template('register.html', user=get_current_user())

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin_secret = request.form.get('admin_secret')

        if admin_secret != 'chitkara@123':
            flash('❌ Invalid Admin Secret Key!', 'error')
            return redirect(url_for('admin_register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'error')
            return redirect(url_for('admin_register'))

        pwd_hash = generate_password_hash(password)
        new_user = User(username=username, password_hash=pwd_hash, role='admin')
        db.session.add(new_user)
        db.session.commit()
        
        flash('Admin registration successful. Please login.', 'success')
        return redirect(url_for('home'))
    return render_template('admin_register.html', user=get_current_user())

@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if role not in ['student', 'admin']:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()

        if not user:
            flash(f'❌ No account found for "{username}". Please register first.', 'error')
            return redirect(url_for('login', role=role))
            
        if user.role != role:
            flash(f'❌ This account is registered as a {user.role.upper()}. Please use the correct login portal.', 'error')
            return redirect(url_for('login', role=role))

        if check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('student_dashboard'))
        
        flash('❌ Incorrect password! Please try again.', 'error')
        return redirect(url_for('login', role=role))
    
    template = 'admin_login.html' if role == 'admin' else 'student_login.html'
    return render_template(template, user=get_current_user())

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def student_dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for('home'))
    if user.role != 'student':
        flash('Please login as a student to access this dashboard.', 'warning')
        return redirect(url_for('home'))
    cities = db.session.query(Center.city).distinct().all()
    cities = [c[0] for c in cities]
    return render_template('student.html', user=user, cities=cities)

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    user = get_current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('home'))
    
    global global_nlp_data
    centers = Center.query.all()
    students = User.query.filter_by(role='student').all()
    seating_assignments = StudentSeating.query.all()
    total_seats = len(seating_assignments)
    total_teacher_duties = TeacherDuty.query.count()
    teacher_duties = TeacherDuty.query.all()
    preview_data = seating_assignments if seating_assignments else None
    teacher_preview = session.get('teacher_preview') if session.get('teacher_preview') else None

    return render_template('admin.html', user=user, centers=centers, students=students, 
                           preview_data=preview_data, total_seats=total_seats, 
                           total_teacher_duties=total_teacher_duties, 
                           teacher_duties=teacher_duties,
                             teacher_preview=teacher_preview)

@app.route('/admin/upload_master', methods=['POST'])
def upload_master():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Unauthorized. Only Admins can upload master seating PDFs.', 'error')
        return redirect(url_for('home'))

    if 'file' not in request.files:
        flash('No file explicitly selected.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        flash('Please select a valid PDF file.', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        extracted = process_pdf(file)
        if not extracted:
            flash('No tabular student data found in the PDF. Please ensure format.', 'error')
            return redirect(url_for('admin_dashboard'))
        StudentSeating.query.delete()
        Seat.query.delete()
        Center.query.delete()
        db.session.commit()
        
        for s in extracted:
            assignment = StudentSeating(
                roll_no=str(s.get('roll_no', 'N/A')),
                name=s.get('name', 'N/A'),
                block=s.get('block', 'Unknown'),
                row=str(s.get('row', 'N/A')),
                seat=str(s.get('seat', 'N/A')),
                exam_date=s.get('exam_date', ''),
                time=s.get('time', '')
            )
            db.session.add(assignment)
            block_name = s.get('block', 'Unknown Building')
            city = s.get('exam_date', 'Local Campus')  
            center = Center.query.filter_by(name=block_name).first()
            if not center:
                center = Center(name=block_name, city=city)
                db.session.add(center)
                db.session.commit()
            
            seat_info = f"Roll: {s.get('roll_no', 'N/A')}, Name: {s.get('name', 'N/A')}, Row: {s.get('row', 'N/A')}, Seat: {s.get('seat', 'N/A')}"
            new_seat = Seat(center_id=center.id, seat_number=seat_info, is_available=False)
            db.session.add(new_seat)
            
        db.session.commit()
        flash(f'✅ Successfully parsed and saved {len(extracted)} student records permanently.', 'success')
        session['extracted_preview'] = extracted[:5]
    except Exception as e:
        flash(f'An error occurred parsing the PDF: {str(e)}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/generate_seating', methods=['POST'])
def generate_seating():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))

    try:
        start_roll = int(request.form.get('start_roll'))
        end_roll = int(request.form.get('end_roll'))
        blocks_raw = request.form.get('block', 'General')
        blocks = [b.strip() for b in blocks_raw.split(',') if b.strip()]
        clear_existing = request.form.get('clear_existing') == 'on'

        if start_roll > end_roll:
            flash('Start Roll No cannot be greater than End Roll No.', 'error')
            return redirect(url_for('admin_dashboard'))

        if clear_existing:
            StudentSeating.query.delete()
            db.session.commit()

        total_students = (end_roll - start_roll) + 1
        num_blocks = len(blocks)
        students_per_block = total_students // num_blocks
        
        count = 0
        for i, roll in enumerate(range(start_roll, end_roll + 1)):
            block_idx = min(i // students_per_block if students_per_block > 0 else 0, num_blocks - 1)
            current_block = blocks[block_idx]
            block_student_count = i % students_per_block if students_per_block > 0 else i
            
            row_num = (block_student_count // 10) + 1
            seat_num = (block_student_count % 10) + 1
            
            assignment = StudentSeating(
                roll_no=str(roll),
                name="N/A",
                block=current_block,
                row=str(row_num),
                seat=str(seat_num),
                exam_date="Generated",
                time="Generated"
            )
            db.session.add(assignment)
            count += 1
        
        db.session.commit()
        flash(f'✅ Successfully generated {count} student seating assignments across {num_blocks} blocks.', 'success')
    except Exception as e:
        flash(f'Error generating seating: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/download_pdf')
def download_pdf():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))

    seating_data = StudentSeating.query.all()
    if not seating_data:
        flash('No seating data to download.', 'error')
        return redirect(url_for('admin_dashboard'))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Times", "B", 16)
    pdf.cell(0, 10, "Exam Seating Arrangement", ln=True, align="C")
    pdf.set_font("Times", "", 12)
    pdf.cell(0, 10, f"Total Students: {len(seating_data)}", ln=True, align="C")
    pdf.ln(5)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Times", "B", 11)
    pdf.cell(50, 10, "Roll No", border=1, align="C", fill=True)
    pdf.cell(50, 10, "Block", border=1, align="C", fill=True)
    pdf.cell(40, 10, "Row", border=1, align="C", fill=True)
    pdf.cell(40, 10, "Seat", border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Times", "", 11)
    for row in seating_data:
        pdf.cell(50, 10, str(row.roll_no), border=1, align="C")
        pdf.cell(50, 10, str(row.block), border=1, align="C")
        pdf.cell(40, 10, str(row.row), border=1, align="C")
        pdf.cell(40, 10, str(row.seat), border=1, align="C")
        pdf.ln()
    from flask import make_response
    response = make_response(bytes(pdf.output()))
    response.headers.set('Content-Type', 'application/pdf')
    response.headers.set('Content-Disposition', 'attachment', filename='seating_plan.pdf')
    return response

@app.route('/admin/clear_seating')
def clear_seating():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    StudentSeating.query.delete()
    Seat.query.delete()
    Center.query.delete()
    db.session.commit()
    flash(' All seating data has been cleared.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload_teacher_master', methods=['POST'])
def upload_teacher_master():
    user = get_current_user()
    if not user or user.role != 'admin':
        flash('Unauthorized. Only Admins can upload duty PDFs.', 'error')
        return redirect(url_for('home'))

    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        flash('Invalid PDF file.', 'error')
        return redirect(url_for('admin_dashboard'))

    try:
        extracted = process_pdf(file)
        if not extracted:
            flash('No teacher duty data found in PDF.', 'error')
            return redirect(url_for('admin_dashboard'))
        
        TeacherDuty.query.delete() 
        db.session.commit()

        for t in extracted:
            final_exam_name = t.get('exam_name') or request.form.get('exam_name_extra') or 'Examination'
            
            new_duty = TeacherDuty(
                teacher_id=str(t.get('roll_no', 'N/A')),
                name=t.get('name', 'N/A'),
                exam_name=final_exam_name,
                block=t.get('block', 'N/A'),
                date=t.get('exam_date') or request.form.get('exam_date_extra'),
                time=t.get('time') or request.form.get('exam_time_extra')
            )
            db.session.add(new_duty)
        db.session.commit()
        
        session['teacher_preview'] = extracted[:10]
        flash(f'✅ Successfully uploaded {len(extracted)} teacher duties.', 'success')
    except Exception as e:
        flash(f'Error processing PDF: {str(e)}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/search_teacher', methods=['POST'])
def search_teacher():
    data = request.get_json()
    if not data:
        return {'success': False, 'message': 'Invalid request'}
    query = data.get('query', '').strip()
    
    duties = TeacherDuty.query.all()
    if not duties:
        return {'success': False, 'message': 'No duty data uploaded yet.'}
    match = TeacherDuty.query.filter(
        (TeacherDuty.teacher_id.ilike(query)) | 
        (TeacherDuty.name.ilike(query)) |
        (TeacherDuty.name.ilike(f"%{query}%"))
    ).first()
    
    if match:
        return {'success': True, 'data': {
            'name': match.name,
            'id': match.teacher_id,
            'block': match.block,
            'date': match.date,
            'time': match.time,
            'exam': match.exam_name,
            'coords': get_block_coords(match.block)
        }}
    names = [d.name for d in duties if d.name]
    ids = [d.teacher_id for d in duties if d.teacher_id]
    best_name, score_name = process.extractOne(query, names, scorer=fuzz.token_set_ratio) if names else (None, 0)
    best_id, score_id = process.extractOne(query, ids, scorer=fuzz.token_set_ratio) if ids else (None, 0)
    
    if max(score_name, score_id) >= 70: 
        if score_name >= score_id:
            m = TeacherDuty.query.filter_by(name=best_name).first()
        else:
            m = TeacherDuty.query.filter_by(teacher_id=best_id).first()
            
        return {'success': True, 'data': {
            'name': m.name,
            'id': m.teacher_id,
            'block': m.block,
            'date': m.date,
            'time': m.time,
            'exam': m.exam_name,
            'coords': get_block_coords(m.block)
        }}

    return {'success': False, 'message': 'Teacher not found.'}

@app.route('/admin/delete_teacher_duty/<int:duty_id>')
def delete_teacher_duty(duty_id):
    admin = get_current_user()
    if not admin or admin.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    duty = TeacherDuty.query.get(duty_id)
    if duty:
        name = duty.name
        db.session.delete(duty)
        db.session.commit()
        flash(f"Duty for '{name}' deleted.", "success")
    return redirect(url_for('admin_dashboard'))
@app.route('/api/search_roll', methods=['POST'])
def search_roll():
    data = request.get_json()
    if not data:
        return {'success': False, 'message': 'Invalid request Format'}
    query_roll = data.get('roll_no', '').strip()
    seating_data = StudentSeating.query.all()
    if not seating_data:
        return {'success': False, 'message': 'Admin has not uploaded any seating arrangement yet!'}
    
    rolls = [str(record.roll_no) for record in seating_data]
    best_match, score = process.extractOne(query_roll, rolls, scorer=fuzz.ratio)
    
    if score >= 80:
        match_record = StudentSeating.query.filter_by(roll_no=best_match).first()
        return {
            'success': True,
            'data': {
                'roll_no': match_record.roll_no,
                'name': match_record.name,
                'block': match_record.block,
                'row': match_record.row,
                'seat': match_record.seat,
                'exam_date': match_record.exam_date,
                'time': match_record.time,
                'match_type': 'Exact Match' if score == 100 else f'Fuzzy Match ({score}%)',
                'coords': get_block_coords(match_record.block)
            }
        }
    return {'success': False, 'message': f'Roll Number {query_roll} not found in the seating plan.'}

@app.route('/api/search', methods=['GET'])
def search_seats():
    query = request.args.get('q', '').lower()
    search_type = request.args.get('type', 'city')

    if search_type == 'city':
        centers = Center.query.filter(Center.city.ilike(f'%{query}%')).all()
    else:
        centers = Center.query.filter(Center.name.ilike(f'%{query}%')).all()

    results = []
    for c in centers:
        available_seats = Seat.query.filter_by(center_id=c.id, is_available=True).count()
        total_seats = Seat.query.filter_by(center_id=c.id).count()
        results.append({
            'center_name': c.name,
            'city': c.city,
            'available': available_seats,
            'total': total_seats
        })
    
    return {'success': True, 'data': results}

@app.route('/api/upload_admit_card', methods=['POST'])
def upload_admit_card():
    user = get_current_user()
    if not user or user.role != 'student':
        flash('Unauthorized. Only students can upload admit cards.', 'error')
        return redirect(url_for('home'))

    if 'file' not in request.files:
        flash('No file part in upload request.', 'error')
        return redirect(url_for('student_dashboard'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file was selected.', 'error')
        return redirect(url_for('student_dashboard'))
    if not file.filename.lower().endswith('.pdf'):
        flash('Only standard PDF files are allowed.', 'error')
        return redirect(url_for('student_dashboard'))

    filename = secure_filename(f"user_{user.id}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    user.admit_card_file = filename
    db.session.commit()
    flash('✅ Admit card securely uploaded!', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    admin = get_current_user()
    if not admin or admin.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
        
    student = User.query.get(user_id)
    if student:
        if student.admit_card_file:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], student.admit_card_file)
            if os.path.exists(filepath):
                os.remove(filepath)
        
        username = student.username
        db.session.delete(student)
        db.session.commit()
        flash(f"User '{username}' has been deleted.", "success")
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/delete_admit_card/<int:user_id>')
def delete_admit_card(user_id):
    admin = get_current_user()
    if not admin or admin.role != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('home'))
    student = User.query.get(user_id)
    if student and student.admit_card_file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], student.admit_card_file)
        if os.path.exists(filepath):
            os.remove(filepath)
        student.admit_card_file = None
        db.session.commit()
        flash(f"Admit card deleted.", "success")
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
