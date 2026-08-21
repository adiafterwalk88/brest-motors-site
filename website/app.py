import os
import re
from datetime import datetime, timedelta
from functools import wraps

import bcrypt
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g
)
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from flask_wtf import CSRFProtect
from psycopg2 import pool
from psycopg2.extras import DictCursor
from wtforms import StringField, FloatField, SelectField, TextAreaField, TelField
from wtforms.validators import DataRequired, Email, Optional, Length, Regexp

load_dotenv()

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

class Config:
    # Безопасность
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    SITE_NAME = 'InTarget Brest Motors'

    # Сессии (Redis)
    SESSION_TYPE = 'redis'
    SESSION_REDIS = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'brest_motors:session:'

    # Кеширование
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    CACHE_DEFAULT_TIMEOUT = 300

    # База данных (пул соединений)
    DB_POOL_MIN = 2
    DB_POOL_MAX = 10

    # Магазины
    SHOPS = {
        'moskovskaya': '🏪 ул. Московская, 123',
        'kariernaya': '🏪 ул. Карьерная, 45'
    }

    # Сотрудники (пароли хешированы!)
    EMPLOYEES = [
        {'id': 'pavel_ivanovich', 'name': 'Павел Иванович', 'password_hash': os.environ.get('PASSWORD_HASH_PAVEL_IVANOVICH')},
        {'id': 'pavel', 'name': 'Павел', 'password_hash': os.environ.get('PASSWORD_HASH_PAVEL')},
        {'id': 'dmitry', 'name': 'Дмитрий', 'password_hash': os.environ.get('PASSWORD_HASH_DMITRY')},
        {'id': 'alexander', 'name': 'Александр', 'password_hash': os.environ.get('PASSWORD_HASH_ALEXANDER')}
    ]

# Проверка конфигурации
if not Config.ADMIN_PASSWORD_HASH:
    raise ValueError("❌ ADMIN_PASSWORD_HASH не найден! Сгенерируйте его: python generate_hash.py")
if not Config.DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден!")

# ==========================================
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ==========================================

app = Flask(__name__)
app.config.from_object(Config)

# Защита от CSRF
csrf = CSRFProtect(app)

# Сессии через Redis
Session(app)

# Кеширование
cache = Cache(app)

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=app.config['CACHE_REDIS_URL']
)

# Пул соединений с БД
db_pool = None

def init_db_pool():
    global db_pool
    try:
        db_pool = pool.SimpleConnectionPool(
            app.config['DB_POOL_MIN'],
            app.config['DB_POOL_MAX'],
            app.config['DATABASE_URL']
        )
        print("✅ Пул соединений с БД создан")
    except Exception as e:
        print(f"❌ Ошибка создания пула: {e}")
        raise

def get_db_connection():
    """Получить соединение из пула"""
    if db_pool is None:
        init_db_pool()
    return db_pool.getconn()

def release_db_connection(conn):
    """Вернуть соединение в пул"""
    if db_pool and conn:
        db_pool.putconn(conn)

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def hash_password(password: str) -> str:
    """Хеширование пароля"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Проверка пароля"""
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def safe_float(value, default=0.0):
    if not value or not str(value).strip():
        return default
    try:
        return float(str(value).strip().replace(',', '.'))
    except ValueError:
        return default

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in') or not session.get('is_admin'):
            flash('Доступ запрещен. Требуются права администратора.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_shop():
    return session.get('shop_id', 'moskovskaya')

def get_employee_names():
    return [emp['name'] for emp in Config.EMPLOYEES if emp.get('name')]

def get_employee_by_id(emp_id):
    for emp in Config.EMPLOYEES:
        if emp['id'] == emp_id:
            return emp
    return None

def format_phone(phone: str) -> str:
    """Форматирование телефона +375 (XX) XXX-XX-XX"""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('375') and len(digits) == 12:
        return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"
    return phone

# ==========================================
# WTForms ДЛЯ ЗАКАЗОВ
# ==========================================

class OrderForm:
    """Класс-контейнер для валидации заказов"""
    
    @staticmethod
    def validate(data):
        errors = {}
        
        if not data.get('customer', '').strip():
            errors['customer'] = 'Обязательное поле'
        elif len(data['customer'].strip()) < 2:
            errors['customer'] = 'Минимум 2 символа'
            
        if not data.get('phone', '').strip():
            errors['phone'] = 'Обязательное поле'
        elif len(re.sub(r'\D', '', data['phone'])) < 9:
            errors['phone'] = 'Введите корректный номер телефона'
            
        if not data.get('product', '').strip():
            errors['product'] = 'Обязательное поле'
        elif len(data['product'].strip()) < 3:
            errors['product'] = 'Минимум 3 символа'
            
        price = safe_float(data.get('price'))
        if price < 0:
            errors['price'] = 'Цена не может быть отрицательной'
            
        prepaid = safe_float(data.get('prepaid'))
        if prepaid < 0:
            errors['prepaid'] = 'Предоплата не может быть отрицательной'
        elif prepaid > price:
            errors['prepaid'] = 'Предоплата не может быть больше цены'
            
        return errors

# ==========================================
# МАРШРУТЫ АВТОРИЗАЦИИ
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')
        
        if login_type == 'admin':
            password = request.form.get('password')
            shop_id = request.form.get('shop_id', 'moskovskaya')
            
            if verify_password(password, Config.ADMIN_PASSWORD_HASH):
                session.permanent = True
                session['logged_in'] = True
                session['is_admin'] = True
                session['user_id'] = 'admin'
                session['user_name'] = 'Администратор'
                session['shop_id'] = shop_id
                session['shop_name'] = Config.SHOPS.get(shop_id, 'ул. Московская, 123')
                flash('✅ Добро пожаловать, Администратор!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('❌ Неверный пароль!', 'error')
        
        elif login_type == 'employee':
            employee_id = request.form.get('employee_id')
            password = request.form.get('password')
            
            employee = get_employee_by_id(employee_id)
            if employee and verify_password(password, employee.get('password_hash')):
                session.permanent = True
                session['logged_in'] = True
                session['is_admin'] = False
                session['user_id'] = employee['id']
                session['user_name'] = employee['name']
                session['shop_id'] = 'all'
                session['shop_name'] = 'Все магазины'
                flash(f'✅ Добро пожаловать, {employee["name"]}!', 'success')
                return redirect(url_for('employee_dashboard'))
            else:
                flash('❌ Неверный ID или пароль!', 'error')
    
    return render_template('login.html', shops=Config.SHOPS, employees=Config.EMPLOYEES)

@app.route('/logout')
def logout():
    try:
        if session.get('user_id'):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_sessions 
                SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (session.get('user_id'),))
            conn.commit()
            cur.close()
            release_db_connection(conn)
    except:
        pass
    
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/switch-shop/<shop_id>')
@login_required
def switch_shop(shop_id):
    if shop_id in Config.SHOPS:
        session['shop_id'] = shop_id
        session['shop_name'] = Config.SHOPS[shop_id]
        flash(f'🔄 Переключено на {session["shop_name"]}', 'success')
    return redirect(request.referrer or url_for('dashboard'))

# ==========================================
# ГЕНЕРАТОР ХЕШЕЙ (утилита)
# ==========================================

@app.cli.command('generate-hashes')
def generate_hashes_command():
    """Генерация хешей для паролей"""
    print("\n🔑 Генерация хешей паролей:")
    print("=" * 50)
    
    # Для администратора
    admin_password = input("Введите пароль администратора: ").strip()
    if admin_password:
        print(f"ADMIN_PASSWORD_HASH={hash_password(admin_password)}")
    
    print("\nДля сотрудников:")
    for emp in Config.EMPLOYEES:
        pwd = input(f"Введите пароль для {emp['name']}: ").strip()
        if pwd:
            print(f"PASSWORD_HASH_{emp['id'].upper()}={hash_password(pwd)}")
    
    print("\n✅ Добавьте эти строки в файл .env")

# ==========================================
# АДМИН-ПАНЕЛЬ (улучшенная)
# ==========================================

@app.route('/')
@login_required
@cache.cached(timeout=60, unless=lambda: not session.get('is_admin'))
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('employee_dashboard'))
    
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        if shop_id == 'all':
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50;")
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders;")
            total_orders, active_orders = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
            today_orders = cur.fetchone()[0]
            
            cur.execute("""
                SELECT status, COUNT(*) FROM orders GROUP BY status;
            """)
            status_stats = cur.fetchall()
        else:
            cur.execute("SELECT * FROM orders WHERE shop_id = %s ORDER BY created_at DESC LIMIT 50;", (shop_id,))
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders WHERE shop_id = %s;", (shop_id,))
            total_orders, active_orders = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND created_at::date = CURRENT_DATE;", (shop_id,))
            today_orders = cur.fetchone()[0]
            
            cur.execute("""
                SELECT status, COUNT(*) FROM orders WHERE shop_id = %s GROUP BY status;
            """, (shop_id,))
            status_stats = cur.fetchall()
        
        cur.close()
        release_db_connection(conn)
        
        return render_template('dashboard.html',
                             orders=orders,
                             total_orders=total_orders or 0,
                             active_orders=active_orders or 0,
                             today_orders=today_orders or 0,
                             status_stats=status_stats,
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES)
    except Exception as e:
        print(f"Ошибка дашборда: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('dashboard.html', orders=[], shops=Config.SHOPS, employees=Config.EMPLOYEES)

# ==========================================
# ЗАКАЗЫ (улучшенные, с пагинацией и валидацией)
# ==========================================

@app.route('/orders')
@login_required
def orders_page():
    try:
        shop_id = get_user_shop()
        search = request.args.get('search', '')
        order_id_search = request.args.get('order_id', '')
        status_filter = request.args.get('status', '')
        executor_filter = request.args.get('executor', '')
        show_archived = request.args.get('show_archived', 'false') == 'true'
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Базовый запрос
        query = "SELECT * FROM orders WHERE shop_id = %s"
        count_query = "SELECT COUNT(*) FROM orders WHERE shop_id = %s"
        params = [shop_id]
        
        # Фильтры
        if not show_archived:
            query += " AND is_archived = FALSE"
            count_query += " AND is_archived = FALSE"
        
        if order_id_search and order_id_search.isdigit():
            query += " AND id = %s"
            count_query += " AND id = %s"
            params.append(int(order_id_search))
        
        if search:
            search_pattern = f"%{search}%"
            query += " AND (customer ILIKE %s OR phone ILIKE %s OR product ILIKE %s)"
            count_query += " AND (customer ILIKE %s OR phone ILIKE %s OR product ILIKE %s)"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if status_filter:
            query += " AND status = %s"
            count_query += " AND status = %s"
            params.append(status_filter)
        
        if executor_filter:
            query += " AND executor = %s"
            count_query += " AND executor = %s"
            params.append(executor_filter)
        
        # Пагинация
        offset = (page - 1) * per_page
        query += f" ORDER BY created_at DESC LIMIT {per_page} OFFSET {offset};"
        
        # Счетчик для пагинации
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]
        
        # Получение заказов
        cur.execute(query, params)
        orders = cur.fetchall()
        
        # Получение статусов для фильтра
        cur.execute("SELECT DISTINCT status FROM orders WHERE shop_id = %s;", (shop_id,))
        statuses = [row['status'] for row in cur.fetchall()]
        
        # Кол-во в архиве
        cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND is_archived = TRUE;", (shop_id,))
        archived_count = cur.fetchone()[0]
        
        cur.close()
        release_db_connection(conn)
        
        return render_template('orders.html',
                             orders=orders,
                             statuses=statuses,
                             executors=get_employee_names(),
                             employees=Config.EMPLOYEES,
                             search=search,
                             order_id_search=order_id_search,
                             current_status=status_filter,
                             current_executor=executor_filter,
                             show_archived=show_archived,
                             archived_count=archived_count,
                             shops=Config.SHOPS,
                             page=page,
                             total_pages=(total_count + per_page - 1) // per_page,
                             total_count=total_count)
    except Exception as e:
        print(f"Ошибка заказов: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('orders.html', orders=[], statuses=[], executors=[], employees=[], shops=Config.SHOPS)

@app.route('/orders/create', methods=['GET'])
@login_required
def create_order_form():
    return render_template('create_order.html', shops=Config.SHOPS, employees=Config.EMPLOYEES)

@app.route('/orders/add', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def add_order():
    try:
        # Валидация
        errors = OrderForm.validate(request.form)
        if errors:
            for field, error in errors.items():
                flash(f'❌ {field}: {error}', 'error')
            return redirect(url_for('create_order_form'))
        
        shop_id = get_user_shop()
        customer = request.form.get('customer').strip()
        phone = request.form.get('phone').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product').strip()
        price = safe_float(request.form.get('price'))
        prepaid = safe_float(request.form.get('prepaid'))
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                               priority, executor, status, comment, shop_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (customer, phone, address, product, price, prepaid, priority, executor, 
              status, comment, shop_id, session.get('user_name')))
        order_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        # Очистка кеша
        cache.delete_memoized(dashboard)
        
        flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка создания: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['GET'])
@login_required
def edit_order_form(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        order = cur.fetchone()
        cur.close()
        release_db_connection(conn)
        
        if not order:
            flash('❌ Заказ не найден!', 'error')
            return redirect(url_for('orders_page'))
        
        return render_template('edit_order.html', order=order, shops=Config.SHOPS, employees=Config.EMPLOYEES)
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки заказа', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    try:
        shop_id = get_user_shop()
        
        # Валидация
        errors = OrderForm.validate(request.form)
        if errors:
            for field, error in errors.items():
                flash(f'❌ {field}: {error}', 'error')
            return redirect(url_for('edit_order_form', order_id=order_id))
        
        customer = request.form.get('customer').strip()
        phone = request.form.get('phone').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product').strip()
        price = safe_float(request.form.get('price'))
        prepaid = safe_float(request.form.get('prepaid'))
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            release_db_connection(conn)
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders 
            SET customer = %s, phone = %s, address = %s, product = %s, 
                price = %s, prepaid = %s, priority = %s, executor = %s, 
                status = %s, comment = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND shop_id = %s
            RETURNING id;
        """, (customer, phone, address, product, price, prepaid, priority, executor, 
              status, comment, order_id, shop_id))
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        # Очистка кеша
        cache.delete_memoized(dashboard)
        
        flash(f'✅ Заказ #{order_id} успешно обновлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка редактирования: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/update', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def update_order(order_id):
    try:
        shop_id = get_user_shop()
        status = request.form.get('status')
        executor = request.form.get('executor')
        employee_notes = request.form.get('employee_notes', '').strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            release_db_connection(conn)
            return redirect(url_for('orders_page'))
        
        completed_at = 'CURRENT_TIMESTAMP' if status == 'Выдан' else 'NULL'
        
        cur.execute(f"""
            UPDATE orders 
            SET status = %s, executor = %s, employee_notes = %s,
                completed_at = {completed_at}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND shop_id = %s;
        """, (status, executor, employee_notes, order_id, shop_id))
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        # Очистка кеша
        cache.delete_memoized(dashboard)
        
        flash(f'✅ Заказ #{order_id} обновлен!', 'success')
        return redirect(request.referrer or url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка обновления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(request.referrer or url_for('orders_page'))

@app.route('/orders/<int:order_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_order(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            release_db_connection(conn)
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders SET is_archived = TRUE, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND shop_id = %s;
        """, (order_id, shop_id))
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        cache.delete_memoized(dashboard)
        flash(f'📦 Заказ #{order_id} перемещен в архив!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка архивации: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/unarchive', methods=['POST'])
@login_required
@admin_required
def unarchive_order(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            release_db_connection(conn)
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders SET is_archived = FALSE, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND shop_id = %s;
        """, (order_id, shop_id))
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        cache.delete_memoized(dashboard)
        flash(f'📤 Заказ #{order_id} восстановлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка восстановления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/soft-delete', methods=['POST'])
@login_required
@admin_required
def soft_delete_order(order_id):
    """Мягкое удаление (помечаем, но не удаляем физически)"""
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            release_db_connection(conn)
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND shop_id = %s;
        """, (order_id, shop_id))
        conn.commit()
        cur.close()
        release_db_connection(conn)
        
        cache.delete_memoized(dashboard)
        flash(f'🗑️ Заказ #{order_id} помечен как удаленный', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка удаления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# API УВЕДОМЛЕНИЙ (улучшенный)
# ==========================================

@app.route('/api/notifications/check')
@login_required
@limiter.limit("60 per minute")
def check_notifications_api():
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Новые заказы для сотрудника
        cur.execute("""
            SELECT COUNT(*) FROM orders 
            WHERE executor = %s AND status = 'Новый' AND is_archived = FALSE AND deleted_at IS NULL
        """, (user_name,))
        new_orders = cur.fetchone()[0]
        
        # Непрочитанные уведомления
        cur.execute("""
            SELECT COUNT(*) FROM notifications 
            WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE
        """, (user_id,))
        unread = cur.fetchone()[0]
        
        # Просроченные заказы
        cur.execute("""
            SELECT id, customer, created_at, status 
            FROM orders 
            WHERE executor = %s AND status != 'Выдан' AND deleted_at IS NULL
        """, (user_name,))
        orders = cur.fetchall()
        
        cur.close()
        release_db_connection(conn)
        
        overdue_orders = []
        for order in orders:
            if order['created_at'] and datetime.now() - order['created_at'] > timedelta(hours=48):
                overdue_orders.append(order['id'])
                # Создаем уведомление о просрочке (если еще нет)
                create_notification(
                    user_id=user_id,
                    user_name=user_name,
                    title=f"⚠️ Заказ #{order['id']} просрочен!",
                    message=f"Заказ для {order['customer']} создан более 48 часов назад",
                    order_id=order['id'],
                    priority='Высокий',
                    action_url="/orders"
                )
        
        return jsonify({
            'new_orders': new_orders,
            'unread': unread,
            'overdue': len(overdue_orders),
            'overdue_ids': overdue_orders
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# ЗАПУСК
# ==========================================

if __name__ == '__main__':
    init_db_pool()
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
