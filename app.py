from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import random
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    cv_path = db.Column(db.String(255))
    id_front_path = db.Column(db.String(255))
    id_back_path = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    test_score = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bids = db.relationship('Bid', backref='applicant', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    client_name = db.Column(db.String(100), nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='open')
    bids = db.relationship('Bid', backref='task', lazy=True)

class Bid(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    bid_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=False)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False) 
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # a, b, c, or d

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_file(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return filepath
    return None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/safety')
def safety():
    return render_template('safety.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_approved and not user.is_admin:
                flash('Your account is pending approval.', 'warning')
                return redirect(url_for('login'))
            
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login failed. Please check your email and password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        
        # Validate phone is US or UK format
        if not (phone.startswith('+1') or phone.startswith('+44')):
            flash('Please enter a valid US (+1) or UK (+44) phone number.', 'danger')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        
        # Handle file uploads
        cv_file = request.files.get('cv')
        id_front = request.files.get('id_front')
        id_back = request.files.get('id_back')
        
        cv_path = save_file(cv_file)
        id_front_path = save_file(id_front)
        id_back_path = save_file(id_back)
        
        if not (cv_path and id_front_path and id_back_path):
            flash('All documents must be uploaded.', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone,
            cv_path=cv_path,
            id_front_path=id_front_path,
            id_back_path=id_back_path
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Store user ID in session for the test
        session['pending_user_id'] = new_user.id
        
        return redirect(url_for('skill_test'))
    
    return render_template('register.html')

@app.route('/skill-test', methods=['GET', 'POST'])
def skill_test():
    if 'pending_user_id' not in session:
        return redirect(url_for('register'))
    
    if request.method == 'GET':
        # Get 10 random questions
        questions = Question.query.order_by(db.func.random()).limit(10).all()
        session['test_questions'] = [q.id for q in questions]
        return render_template('skill_test.html', questions=questions)
    
    if request.method == 'POST':
        user = User.query.get(session['pending_user_id'])
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('register'))
        
        # Calculate score
        score = 0
        for q_id in session['test_questions']:
            question = Question.query.get(q_id)
            user_answer = request.form.get(f'q{q_id}')
            if user_answer == question.correct_answer:
                score += 1
        
        # Update user's test score
        user.test_score = score
        db.session.commit()
        
        # Clean up session
        session.pop('pending_user_id', None)
        session.pop('test_questions', None)
        
        flash('Your application has been submitted. Please wait for admin approval.', 'success')
        return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        pending_users = User.query.filter_by(is_approved=False, is_admin=False).all()
        tasks = Task.query.all()
        bids = Bid.query.all()
        users = User.query.filter_by(is_admin=False).all()
        return render_template('admin_dashboard.html', 
                              pending_users=pending_users, 
                              tasks=tasks,
                              bids=bids,
                              users=users)
    else:
        tasks = Task.query.filter_by(status='open').all()
        user_bids = Bid.query.filter_by(user_id=current_user.id).all()
        return render_template('user_dashboard.html', tasks=tasks, bids=user_bids)

@app.route('/approve-user/<int:user_id>')
@login_required
def approve_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    
    flash(f'User {user.email} has been approved.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/restrict-user/<int:user_id>')
@login_required
def restrict_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    user.is_approved = False
    db.session.commit()
    
    flash(f'User {user.email} has been restricted.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/add-task', methods=['GET', 'POST'])
@login_required
def add_task():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        new_task = Task(
            title=request.form.get('title'),
            description=request.form.get('description'),
            client_name=request.form.get('client_name'),
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%d')
        )
        
        db.session.add(new_task)
        db.session.commit()
        
        flash('New task added successfully.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_task.html')

@app.route('/delete-task/<int:task_id>')
@login_required
def delete_task(task_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    
    flash('Task deleted successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/bid/<int:task_id>', methods=['POST'])
@login_required
def place_bid(task_id):
    if current_user.is_admin:
        flash('Admins cannot place bids.', 'danger')
        return redirect(url_for('dashboard'))
    
    task = Task.query.get_or_404(task_id)
    
    # Check if user already bid on this task
    existing_bid = Bid.query.filter_by(user_id=current_user.id, task_id=task_id).first()
    if existing_bid:
        flash('You have already bid on this task.', 'warning')
        return redirect(url_for('dashboard'))
    
    new_bid = Bid(user_id=current_user.id, task_id=task_id)
    db.session.add(new_bid)
    db.session.commit()
    
    flash('Bid placed successfully. Awaiting admin approval.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/approve-bid/<int:bid_id>')
@login_required
def approve_bid(bid_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    bid = Bid.query.get_or_404(bid_id)
    bid.is_approved = True
    db.session.commit()
    
    flash('Bid approved successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/user-details/<int:user_id>')
@login_required
def user_details(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    return render_template('user_details.html', user=user)

#############################

# Create default admin if none exists
with app.app_context():
    if not User.query.filter_by(is_admin=True).first():
        default_admin = User(
            email="admin@example.com",
            password_hash=generate_password_hash("AdminPassword123"),
            phone="000-000-0000",
            is_admin=True,
            is_approved=True
        )
        db.session.add(default_admin)
        db.session.commit()
        print("Default admin created: admin@example.com / AdminPassword123")


###########################

# Admin creation route (should be protected or removed in production)
@app.route('/create-admin/<secret_key>', methods=['GET', 'POST'])
def create_admin():
    if request.args.get('secret_key') != os.environ.get('ADMIN_SECRET', 'change-this-in-production'):
        return "Access Denied", 403
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return redirect(url_for('create_admin', secret_key=request.args.get('secret_key')))
        
        admin = User(
            email=email,
            password_hash=generate_password_hash(password),
            phone="admin",
            is_admin=True,
            is_approved=True
        )
        
        db.session.add(admin)
        db.session.commit()
        
        flash('Admin account created successfully.', 'success')
        return redirect(url_for('login'))
    
    return render_template('create_admin.html')

# Initialize the database and add sample questions
@app.cli.command("init-db")
def init_db():
    db.create_all()
    
    # Add sample questions if none exist
    if Question.query.count() == 0:
        sample_questions = [
            Question(
                question_text="What does HTML stand for?",
                option_a="Hyper Text Markup Language",
                option_b="High Tech Machine Learning",
                option_c="Hyperlinks and Text Markup Language",
                option_d="Home Tool Markup Language",
                correct_answer="a"
            ),
            Question(
                question_text="Which of the following is a Python web framework?",
                option_a="React",
                option_b="Angular",
                option_c="Flask",
                option_d="Express",
                correct_answer="c"
            ),
            Question(
                question_text="What is the purpose of SQL?",
                option_a="Web Design",
                option_b="Database Management",
                option_c="Network Security",
                option_d="Machine Learning",
                correct_answer="b"
            ),
            Question(
                question_text="Which data structure follows LIFO principle?",
                option_a="Queue",
                option_b="Stack",
                option_c="Array",
                option_d="Linked List",
                correct_answer="b"
            ),
            Question(
                question_text="What does CSS stand for?",
                option_a="Computer Style Sheets",
                option_b="Creative Style System",
                option_c="Cascading Style Sheets",
                option_d="Colorful Style Sheets",
                correct_answer="c"
            ),
            Question(
                question_text="Which of these is not a JavaScript framework?",
                option_a="Vue",
                option_b="Django",
                option_c="React",
                option_d="Angular",
                correct_answer="b"
            ),
            Question(
                question_text="What is the time complexity of binary search?",
                option_a="O(n)",
                option_b="O(n²)",
                option_c="O(log n)",
                option_d="O(n log n)",
                correct_answer="c"
            ),
            Question(
                question_text="Which protocol is used for secure web browsing?",
                option_a="HTTP",
                option_b="FTP",
                option_c="HTTPS",
                option_d="SMTP",
                correct_answer="c"
            ),
            Question(
                question_text="What does API stand for?",
                option_a="Application Programming Interface",
                option_b="Advanced Programming Interface",
                option_c="Automated Programming Integration",
                option_d="Application Process Integration",
                correct_answer="a"
            ),
            Question(
                question_text="Which of these is a NoSQL database?",
                option_a="MySQL",
                option_b="PostgreSQL",
                option_c="MongoDB",
                option_d="Oracle",
                correct_answer="c"
            ),
            Question(
                question_text="What does the term 'CI/CD' stand for?",
                option_a="Continuous Integration/Continuous Deployment",
                option_b="Computer Interface/Computer Development",
                option_c="Continuous Iteration/Continuous Development",
                option_d="Code Integration/Code Deployment",
                correct_answer="a"
            ),
            Question(
                question_text="Which data annotation technique is used for image recognition?",
                option_a="Sentiment Analysis",
                option_b="Named Entity Recognition",
                option_c="Bounding Boxes",
                option_d="Text Classification",
                correct_answer="c"
            )
        ]
        
        for question in sample_questions:
            db.session.add(question)
        
        db.session.commit()
        print("Database initialized with sample questions.")

if __name__ == '__main__':
    app.run(debug=False)