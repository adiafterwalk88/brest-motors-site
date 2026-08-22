import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime, Text, Boolean
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ===== Базовый класс для SQLAlchemy =====
class Base(DeclarativeBase):
    pass

# ===== Инициализация приложения =====
app = Flask(__name__)

# ===== Генерация SECRET_KEY, если не задан =====
# ВАЖНО: Для production используйте переменную окружения!
if os.environ.get('FLASK_DEBUG') == 'False' or os.environ.get('RENDER'):
    # Production режим - обязательно используем переменную окружения
    app.secret_key = os.environ.get('SECRET_KEY')
    if not app.secret_key:
        # Если ключ не задан, генерируем временный (НО НЕ ДЕЛАЙТЕ ТАК В PRODUCTION!)
        app.secret_key = secrets.token_hex(32)
        print("⚠️ ВНИМАНИЕ: Используется временный SECRET_KEY. Установите постоянный в переменных окружения!")
else:
    # Development режим
    app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ===== Конфигурация базы данных =====
# Используем PostgreSQL на Render
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    # Render использует postgres://, но SQLAlchemy требует postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# ===== Инициализация БД =====
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# ===== Модели =====
class User(db.Model):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Order(db.Model):
    __tablename__ = 'orders'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default='новый')
    description: Mapped[str] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='orders')

# ===== Декораторы =====
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Доступ запрещен', 'danger')
            return redirect(url_for('orders'))
        return f(*args, **kwargs)
    return decorated_function

# ===== Роуты =====
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('orders'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(url_for('orders'))
        else:
            flash('Неверный email или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email уже используется', 'danger')
            return render_template('register.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/orders')
@login_required
def orders():
    return render_template('orders.html')

@app.route('/api/orders')
@login_required
def api_orders():
    user_id = session['user_id']
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    
    return jsonify([{
        'id': o.id,
        'order_number': o.order_number,
        'client_name': o.client_name,
        'amount': o.amount,
        'status': o.status,
        'description': o.description,
        'created_at': o.created_at.isoformat()
    } for o in orders])

@app.route('/api/orders', methods=['POST'])
@login_required
def api_create_order():
    data = request.json
    user_id = session['user_id']
    
    order = Order(
        order_number=data['order_number'],
        client_name=data['client_name'],
        amount=data['amount'],
        status=data.get('status', 'новый'),
        description=data.get('description', ''),
        user_id=user_id
    )
    
    db.session.add(order)
    db.session.commit()
    
    return jsonify({'id': order.id, 'message': 'Заказ создан'}), 201

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def api_update_order(order_id):
    data = request.json
    user_id = session['user_id']
    
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': 'Заказ не найден'}), 404
    
    order.order_number = data.get('order_number', order.order_number)
    order.client_name = data.get('client_name', order.client_name)
    order.amount = data.get('amount', order.amount)
    order.status = data.get('status', order.status)
    order.description = data.get('description', order.description)
    
    db.session.commit()
    
    return jsonify({'message': 'Заказ обновлен'})

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
@login_required
def api_delete_order(order_id):
    user_id = session['user_id']
    
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': 'Заказ не найден'}), 404
    
    db.session.delete(order)
    db.session.commit()
    
    return jsonify({'message': 'Заказ удален'})

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.all()
    orders = Order.query.all()
    return render_template('admin.html', users=users, orders=orders)

# ===== Создание таблиц =====
with app.app_context():
    db.create_all()
    print("✅ База данных инициализирована")

# ===== Обработка ошибок =====
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
