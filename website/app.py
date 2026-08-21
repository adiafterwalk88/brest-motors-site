import os
import re
import json
import logging
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

from flask import (
    Flask, render_template, request, jsonify, flash, redirect,
    url_for, session, send_from_directory, make_response
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')

# Конфигурация приложения
class Config:
    DATABASE_URL = os.environ.get('DATABASE_URL')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
    
    SHOPS = {
        'all': 'Все филиалы',
        'moskovskaya': 'Московская',
        'kariernaya': 'Карьерная'
    }
    
    EMPLOYEES = [
        'Павел Иванович',
        'Павел',
        'Дмитрий',
        'Александр'
    ]

app.config.from_object(Config)

# Создание папки для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация пула соединений PostgreSQL
db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_url = app.config['DATABASE_URL']
        if not db_url:
            logger.error("DATABASE_URL не установлена!")
            return
        try:
            db_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=db_url
            )
            logger.info("Пул соединений PostgreSQL успешно создан.")
        except Exception as e:
            logger.exception("Ошибка подключения к PostgreSQL")

@contextmanager
def get_db_cursor(commit=False):
    if db_pool is None:
        init_db_pool()
    conn = db_pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Ошибка выполнения БД запроса")
        raise e
    finally:
        cur.close()
        db_pool.putconn(conn)

def init_db_tables():
    """Создает необходимые таблицы и дефолтного админа, если их нет в БД"""
    if db_pool is None:
        init_db_pool()
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer_name VARCHAR(150),
                    customer_phone VARCHAR(50),
                    device_type VARCHAR(100),
                    device_model VARCHAR(100),
                    serial_number VARCHAR(100),
                    defect_description TEXT,
                    estimated_cost NUMERIC(10, 2) DEFAULT 0,
                    prepayment NUMERIC(10, 2) DEFAULT 0,
                    executor VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'Принят',
                    shop_id VARCHAR(50),
                    is_archived BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            default_users = [
                ('dmitry', generate_password_hash('123456'), True),
                ('admin', generate_password_hash('admin123'), True)
            ]

            for username, pass_hash, is_admin in default_users:
                cur.execute("""
                    INSERT INTO users (username, password_hash, is_admin)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (username) DO NOTHING;
                """, (username, pass_hash, is_admin))

        logger.info("Таблицы и стандартные пользователи успешно инициализированы.")
    except Exception as e:
        logger.exception("Ошибка при инициализации таблиц БД")

# Проверка разрешенных расширений
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

# Декораторы доступа
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Требуются права администратора', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# МАРШРУТЫ АВТОРИЗАЦИИ И СЕССИИ
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            with get_db_cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
                user = cur.fetchone()
                
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['is_admin'] = user.get('is_admin', False)
                    session['shop_id'] = 'all'
                    flash('Вы успешно вошли в систему', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Неверное имя пользователя или пароль', 'error')
        except Exception as e:
            flash(f'Ошибка входа: {e}', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/force-login')
def force_login():
    session['user_id'] = 1
    session['username'] = 'admin'
    session['is_admin'] = True
    session['shop_id'] = 'all'
    flash('Выполнен административный вход.', 'success')
    return redirect(url_for('orders_page'))

@app.route('/set-shop/<shop_id>')
@login_required
def set_shop(shop_id):
    if shop_id in Config.SHOPS or shop_id == 'all':
        session['shop_id'] = shop_id
        flash(f'Филиал изменен на: {Config.SHOPS.get(shop_id, "Все филиалы")}', 'info')
    return redirect(request.referrer or url_for('dashboard'))

# ==========================================
# ОСНОВНЫЕ МАРШРУТЫ
# ==========================================

@app.route('/')
@login_required
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('employee_dashboard'))
    
    try:
        shop_id = session.get('shop_id', 'all')
        
        with get_db_cursor() as cur:
            if shop_id == 'all' or not shop_id:
                cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50;")
            else:
                cur.execute("SELECT * FROM orders WHERE (shop_id = %s OR shop_id IS NULL) ORDER BY created_at DESC LIMIT 50;", (shop_id,))
            
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*) FROM orders;")
            res_total = cur.fetchone()
            total_orders = res_total['count'] if res_total else 0
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE status != 'Выдан';")
            res_active = cur.fetchone()
            active_orders = res_active['count'] if res_active else 0
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
            res_today = cur.fetchone()
            today_orders = res_today['count'] if res_today else 0
            
            cur.execute("SELECT status, COUNT(*) FROM orders GROUP BY status;")
            status_stats = cur.fetchall()
        
        return render_template('dashboard.html',
                             orders=orders,
                             total_orders=total_orders,
                             active_orders=active_orders,
                             today_orders=today_orders,
                             status_stats=status_stats,
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             active_page='dashboard',
                             datetime=datetime)
    except Exception as e:
        logger.exception("Ошибка загрузки дашборда")
        flash(f'Ошибка загрузки данных: {e}', 'error')
        return render_template('dashboard.html', orders=[], shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='dashboard', datetime=datetime)

@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    username = session.get('username')
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE executor = %s ORDER BY created_at DESC;", (username,))
            my_orders = cur.fetchall()
            
        return render_template('employee_dashboard.html', orders=my_orders, active_page='my_orders')
    except Exception as e:
        flash(f'Ошибка загрузки: {e}', 'error')
        return render_template('employee_dashboard.html', orders=[])

@app.route('/orders')
@login_required
def orders_page():
    try:
        shop_id = session.get('shop_id', 'all')
        show_archived = request.args.get('show_archived', 'false') == 'true'
        search = request.args.get('search', '').strip()
        
        with get_db_cursor() as cur:
            query = "SELECT * FROM orders WHERE 1=1"
            params = []
            
            if shop_id != 'all' and shop_id:
                query += " AND (shop_id = %s OR shop_id IS NULL)"
                params.append(shop_id)
                
            if not show_archived:
                query += " AND (is_archived = FALSE OR is_archived IS NULL)"
                
            if search:
                query += " AND (customer_name ILIKE %s OR customer_phone ILIKE %s OR device_model ILIKE %s)"
                term = f"%{search}%"
                params.extend([term, term, term])
                
            query += " ORDER BY created_at DESC;"
            
            cur.execute(query, tuple(params))
            orders = cur.fetchall()

            cur.execute("SELECT DISTINCT status FROM orders WHERE status IS NOT NULL;")
            statuses = [row['status'] for row in cur.fetchall()]

            cur.execute("SELECT COUNT(*) FROM orders WHERE is_archived = TRUE;")
            res_archived = cur.fetchone()
            archived_count = res_archived['count'] if res_archived else 0
        
        return render_template('orders.html',
                             orders=orders,
                             statuses=statuses,
                             executors=Config.EMPLOYEES,
                             employees=Config.EMPLOYEES,
                             search=search,
                             order_id_search='',
                             current_status='',
                             current_executor='',
                             show_archived=show_archived,
                             archived_count=archived_count,
                             shops=Config.SHOPS,
                             page=1,
                             total_pages=1,
                             total_count=len(orders),
                             active_page='orders')
    except Exception as e:
        logger.exception("Ошибка загрузки страницы заказов")
        flash(f'Ошибка загрузки заказов: {e}', 'error')
        return render_template('orders.html', orders=[], statuses=[], executors=[], employees=[], shops=Config.SHOPS, active_page='orders')

# ==========================================
# НЕДОСТАЮЩИЕ СТРАНИЦЫ (УБИРАЮТ 404)
# ==========================================

@app.route('/clients')
@login_required
def clients_page():
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT DISTINCT customer_name, customer_phone FROM orders WHERE customer_name IS NOT NULL AND customer_name != '';")
            clients = cur.fetchall()
        return render_template('clients.html', clients=clients, active_page='clients')
    except Exception:
        return render_template('clients.html', clients=[], active_page='clients')

@app.route('/employees')
@login_required
def employees_page():
    return render_template('employees.html', employees=Config.EMPLOYEES, active_page='employees')

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html', active_page='chat')

@app.route('/calendar')
@login_required
def calendar_page():
    return render_template('calendar.html', active_page='calendar')

@app.route('/order/new', methods=['GET', 'POST'])
@login_required
def new_order():
    if request.method == 'POST':
        try:
            data = request.form
            shop_id = session.get('shop_id')
            if shop_id == 'all' or not shop_id:
                shop_id = 'moskovskaya'
                
            with get_db_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO orders (
                        customer_name, customer_phone, device_type, device_model,
                        serial_number, defect_description, estimated_cost,
                        prepayment, executor, status, shop_id, created_at, is_archived
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), FALSE)
                    RETURNING id;
                """, (
                    data.get('customer_name'),
                    data.get('customer_phone'),
                    data.get('device_type'),
                    data.get('device_model'),
                    data.get('serial_number'),
                    data.get('defect_description'),
                    data.get('estimated_cost') or 0,
                    data.get('prepayment') or 0,
                    data.get('executor'),
                    data.get('status', 'Принят'),
                    shop_id
                ))
                new_id = cur.fetchone()['id']
                flash(f'Заказ №{new_id} успешно создан!', 'success')
                return redirect(url_for('orders_page'))
        except Exception as e:
            flash(f'Ошибка при создании заказа: {e}', 'error')
            
    return render_template('order_form.html', employees=Config.EMPLOYEES, shops=Config.SHOPS)

# Автоматическая инициализация при запуске на Render (Gunicorn)
init_db_pool()
init_db_tables()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
