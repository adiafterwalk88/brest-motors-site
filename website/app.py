import os
import re
import logging
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

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
from wtforms.validators import DataRequired, Optional

load_dotenv()

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///brest_motors.db')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'
    SITE_NAME = 'InTarget Brest Motors'
    
    # Сессии (используем файловую систему, если нет Redis)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_sessions'
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    
    # Кеширование (простое)
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # Магазины
    SHOPS = {
        'moskovskaya': '🏪 ул. Московская, 123',
        'kariernaya': '🏪 ул. Карьерная, 45'
    }
    
    # Сотрудники (хеши будут проверяться)
    EMPLOYEES = [
        {'id': 'pavel_ivanovich', 'name': 'Павел Иванович', 'password_hash': os.environ.get('PASSWORD_HASH_PAVEL_IVANOVICH')},
        {'id': 'pavel', 'name': 'Павел', 'password_hash': os.environ.get('PASSWORD_HASH_PAVEL')},
        {'id': 'dmitry', 'name': 'Дмитрий', 'password_hash': os.environ.get('PASSWORD_HASH_DMITRY')},
        {'id': 'alexander', 'name': 'Александр', 'password_hash': os.environ.get('PASSWORD_HASH_ALEXANDER')}
    ]

# Если нет хешей — создаём тестовые
if not Config.ADMIN_PASSWORD_HASH:
    # Пароль: admin123
    Config.ADMIN_PASSWORD_HASH = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')

for emp in Config.EMPLOYEES:
    if not emp.get('password_hash'):
        # Пароль: 123456
        emp['password_hash'] = bcrypt.hashpw(b'123456', bcrypt.gensalt()).decode('utf-8')

# ==========================================
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
# ==========================================

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# CSRF-защита
csrf = CSRFProtect(app)

# Сессии
Session(app)

# Кеширование
cache = Cache(app)

# Rate Limiting (мягкое, для разработки)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ==========================================
# ЛОГГИРОВАНИЕ
# ==========================================

logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('brest_motors')

# ==========================================
# РАБОТА С БАЗОЙ ДАННЫХ (SQLite/PostgreSQL)
# ==========================================

def get_db_connection():
    """Получить соединение с БД"""
    if Config.DATABASE_URL.startswith('sqlite://'):
        db_path = Config.DATABASE_URL.replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        # PostgreSQL
        import psycopg2
        from psycopg2.extras import DictCursor
        conn = psycopg2.connect(Config.DATABASE_URL)
        conn.cursor_factory = DictCursor
        return conn

@contextmanager
def get_db_cursor():
    """Контекстный менеджер для работы с БД"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def init_db():
    """Инициализация базы данных — создание всех таблиц"""
    try:
        with get_db_cursor() as cur:
            # Определяем тип БД
            is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
            
            # Таблица заказов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    address TEXT,
                    product TEXT NOT NULL,
                    price REAL DEFAULT 0,
                    prepaid REAL DEFAULT 0,
                    priority TEXT DEFAULT 'Обычный',
                    executor TEXT,
                    executor_id TEXT,
                    status TEXT DEFAULT 'Новый',
                    comment TEXT,
                    employee_notes TEXT,
                    shop_id TEXT DEFAULT 'moskovskaya',
                    is_archived INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_by TEXT,
                    deleted_at TIMESTAMP
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    address TEXT,
                    product TEXT NOT NULL,
                    price NUMERIC DEFAULT 0,
                    prepaid NUMERIC DEFAULT 0,
                    priority TEXT DEFAULT 'Обычный',
                    executor TEXT,
                    executor_id TEXT,
                    status TEXT DEFAULT 'Новый',
                    comment TEXT,
                    employee_notes TEXT,
                    shop_id TEXT DEFAULT 'moskovskaya',
                    is_archived BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_by TEXT,
                    deleted_at TIMESTAMP
                )
            """)
            
            # Таблица уведомлений
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_name TEXT,
                    order_id INTEGER,
                    notification_type TEXT,
                    title TEXT,
                    message TEXT,
                    priority TEXT DEFAULT 'Обычный',
                    is_read INTEGER DEFAULT 0,
                    is_archived INTEGER DEFAULT 0,
                    scheduled_for TIMESTAMP,
                    action_url TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read_at TIMESTAMP
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT,
                    order_id INTEGER REFERENCES orders(id),
                    notification_type TEXT,
                    title TEXT,
                    message TEXT,
                    priority TEXT DEFAULT 'Обычный',
                    is_read BOOLEAN DEFAULT FALSE,
                    is_archived BOOLEAN DEFAULT FALSE,
                    scheduled_for TIMESTAMP,
                    action_url TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read_at TIMESTAMP
                )
            """)
            
            # Таблица чата
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    user_role TEXT,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    user_role TEXT,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица настроек уведомлений
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    notify_new_orders INTEGER DEFAULT 1,
                    notify_status_changes INTEGER DEFAULT 1,
                    notify_mentions INTEGER DEFAULT 1,
                    notify_overdue INTEGER DEFAULT 1,
                    notify_chat_messages INTEGER DEFAULT 1,
                    notify_assignments INTEGER DEFAULT 1,
                    reminder_frequency INTEGER DEFAULT 60,
                    reminder_start_hour INTEGER DEFAULT 9,
                    reminder_end_hour INTEGER DEFAULT 20,
                    email_notifications INTEGER DEFAULT 0,
                    browser_notifications INTEGER DEFAULT 1,
                    telegram_notifications INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS notification_settings (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    notify_new_orders BOOLEAN DEFAULT TRUE,
                    notify_status_changes BOOLEAN DEFAULT TRUE,
                    notify_mentions BOOLEAN DEFAULT TRUE,
                    notify_overdue BOOLEAN DEFAULT TRUE,
                    notify_chat_messages BOOLEAN DEFAULT TRUE,
                    notify_assignments BOOLEAN DEFAULT TRUE,
                    reminder_frequency INTEGER DEFAULT 60,
                    reminder_start_hour INTEGER DEFAULT 9,
                    reminder_end_hour INTEGER DEFAULT 20,
                    email_notifications BOOLEAN DEFAULT FALSE,
                    browser_notifications BOOLEAN DEFAULT TRUE,
                    telegram_notifications BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица онлайн-сессий
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_online INTEGER DEFAULT 0
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_online BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Таблица аудита
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    user_name TEXT,
                    action TEXT,
                    target_type TEXT,
                    target_id INTEGER,
                    details TEXT,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """ if is_sqlite else """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    user_name TEXT,
                    action TEXT,
                    target_type TEXT,
                    target_id INTEGER,
                    details JSONB,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индексы (для SQLite игнорируем, для PostgreSQL создаём)
            if not is_sqlite:
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_shop_id ON orders(shop_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_is_archived ON orders(is_archived);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_deleted_at ON orders(deleted_at);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);")
                except:
                    pass
            
            print("✅ База данных инициализирована")
            
            # Вставляем тестовые данные, если таблицы пустые
            insert_test_data(cur, is_sqlite)
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

def insert_test_data(cur, is_sqlite):
    """Вставка тестовых данных, если таблицы пустые"""
    
    # Проверяем, есть ли заказы
    cur.execute("SELECT COUNT(*) FROM orders")
    count = cur.fetchone()[0]
    if count > 0:
        return
    
    print("📦 Вставка тестовых данных...")
    
    # Тестовые заказы
    orders = [
        ('Иван Петров', '+375291234567', 'ул. Ленина, 15', 'Ремень генератора Weibang 455SC', 45.00, 20.00, 'Высокий', 'Павел', 'В работе', 'Требуется замена ремня', 'moskovskaya'),
        ('Сергей Сидоров', '+375293334455', 'ул. Пушкина, 7', 'Масляный фильтр + масло 5W-30', 85.50, 85.50, 'Обычный', 'Дмитрий', 'Выдан', 'Оплачено полностью', 'kariernaya'),
        ('Анна Иванова', '+375447778899', 'ул. Советская, 23', 'Комплект тормозных колодок передних', 120.00, 60.00, 'Высокий', 'Павел Иванович', 'Новый', 'Ждёт подтверждения', 'moskovskaya'),
        ('Михаил Козлов', '+375298887766', 'ул. Минская, 45', 'Свечи зажигания NGK (4 шт)', 32.00, 0, 'Низкий', 'Александр', 'Новый', '', 'kariernaya'),
        ('Елена Мороз', '+375336665544', 'ул. Гагарина, 12', 'Аккумулятор 60 Ач', 160.00, 100.00, 'Высокий', 'Павел', 'В работе', 'Замена аккумулятора', 'moskovskaya'),
        ('Алексей Новиков', '+375445554433', 'ул. Партизанская, 8', 'Колодки задние + диски', 210.00, 0, 'Обычный', 'Дмитрий', 'Новый', 'Срочный заказ', 'kariernaya'),
        ('Ольга Смирнова', '+375297774422', 'ул. Кирова, 56', 'Щётки стеклоочистителя (комплект)', 18.00, 18.00, 'Низкий', 'Александр', 'Выдан', '', 'moskovskaya'),
        ('Денис Фёдоров', '+375336668899', 'ул. Калинина, 3', 'Моторное масло 5W-40 (4л)', 55.00, 55.00, 'Обычный', 'Павел Иванович', 'Выдан', '', 'kariernaya'),
    ]
    
    for order in orders:
        if is_sqlite:
            cur.execute("""
                INSERT INTO orders 
                (customer, phone, address, product, price, prepaid, priority, executor, status, comment, shop_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-1 day'))
            """, order)
        else:
            cur.execute("""
                INSERT INTO orders 
                (customer, phone, address, product, price, prepaid, priority, executor, status, comment, shop_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() - INTERVAL '1 day')
            """, order)
    
    # Тестовые сообщения чата
    chat_messages = [
        ('admin', 'Администратор', 'Добро пожаловать в командный чат! 🎯'),
        ('pavel', 'Павел', 'Привет всем! Завтра приезжают новые запчасти.'),
        ('dmitry', 'Дмитрий', 'Отлично, ждём! У меня сегодня 3 заказа на выдачу.'),
        ('alexander', 'Александр', 'Я заканчиваю с заказом #10, буду свободен через час.'),
        ('pavel_ivanovich', 'Павел Иванович', 'Проверьте все заказы перед закрытием смены.'),
    ]
    
    for msg in chat_messages:
        if is_sqlite:
            cur.execute("""
                INSERT INTO chat_messages (user_id, user_name, message, created_at)
                VALUES (?, ?, ?, datetime('now', '-10 minutes'))
            """, msg)
        else:
            cur.execute("""
                INSERT INTO chat_messages (user_id, user_name, message, created_at)
                VALUES (%s, %s, %s, NOW() - INTERVAL '10 minutes')
            """, msg)
    
    print("✅ Тестовые данные добавлены")

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
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

# ==========================================
# SECURITY-ЗАГОЛОВКИ
# ==========================================

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if not Config.DEBUG:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

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
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE user_sessions 
                SET is_online = 0, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (session.get('user_id'),)) if Config.DATABASE_URL.startswith('sqlite://') else cur.execute("""
                UPDATE user_sessions 
                SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (session.get('user_id'),))
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
# АДМИН-ПАНЕЛЬ
# ==========================================

@app.route('/')
@login_required
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('employee_dashboard'))
    
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if shop_id == 'all':
                cur.execute("SELECT * FROM orders WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 50;")
                orders = cur.fetchall()
                
                cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders WHERE deleted_at IS NULL;") if not is_sqlite else cur.execute("SELECT COUNT(*), COUNT(*) FROM orders WHERE status != 'Выдан' AND deleted_at IS NULL;")
                row = cur.fetchone()
                total_orders = row[0] if row else 0
                active_orders = row[1] if row and not is_sqlite else total_orders
                
                cur.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now') AND deleted_at IS NULL;") if is_sqlite else cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE AND deleted_at IS NULL;")
                today_orders = cur.fetchone()[0] or 0
                
                cur.execute("SELECT status, COUNT(*) FROM orders WHERE deleted_at IS NULL GROUP BY status;") if not is_sqlite else cur.execute("SELECT status, COUNT(*) FROM orders WHERE deleted_at IS NULL GROUP BY status;")
                status_stats = cur.fetchall()
            else:
                cur.execute("SELECT * FROM orders WHERE shop_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 50;", (shop_id,)) if is_sqlite else cur.execute("SELECT * FROM orders WHERE shop_id = %s AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 50;", (shop_id,))
                orders = cur.fetchall()
                
                cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders WHERE shop_id = ? AND deleted_at IS NULL;", (shop_id,)) if not is_sqlite else cur.execute("SELECT COUNT(*), COUNT(*) FROM orders WHERE shop_id = ? AND status != 'Выдан' AND deleted_at IS NULL;", (shop_id,))
                row = cur.fetchone()
                total_orders = row[0] if row else 0
                active_orders = row[1] if row and not is_sqlite else total_orders
                
                cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = ? AND DATE(created_at) = DATE('now') AND deleted_at IS NULL;", (shop_id,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND created_at::date = CURRENT_DATE AND deleted_at IS NULL;", (shop_id,))
                today_orders = cur.fetchone()[0] or 0
                
                cur.execute("SELECT status, COUNT(*) FROM orders WHERE shop_id = ? AND deleted_at IS NULL GROUP BY status;", (shop_id,)) if not is_sqlite else cur.execute("SELECT status, COUNT(*) FROM orders WHERE shop_id = ? AND deleted_at IS NULL GROUP BY status;", (shop_id,))
                status_stats = cur.fetchall()
        
        return render_template('dashboard.html',
                             orders=orders,
                             total_orders=total_orders or 0,
                             active_orders=active_orders or 0,
                             today_orders=today_orders or 0,
                             status_stats=status_stats,
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             active_page='dashboard',
                             datetime=datetime)
    except Exception as e:
        logger.exception("Ошибка дашборда")
        flash('Ошибка загрузки данных', 'error')
        return render_template('dashboard.html', orders=[], shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='dashboard', datetime=datetime)

# ==========================================
# КАБИНЕТ СОТРУДНИКА
# ==========================================

@app.route('/employee')
@login_required
def employee_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('dashboard'))
    
    try:
        user_name = session.get('user_name')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            orders_by_shop = {}
            for shop_id, shop_name in Config.SHOPS.items():
                cur.execute("""
                    SELECT * FROM orders 
                    WHERE shop_id = ? AND status != 'Выдан' AND is_archived = 0 AND deleted_at IS NULL
                    ORDER BY 
                        CASE priority 
                            WHEN 'Высокий' THEN 1 
                            WHEN 'Обычный' THEN 2 
                            ELSE 3 
                        END,
                        created_at ASC
                """, (shop_id,)) if is_sqlite else cur.execute("""
                    SELECT * FROM orders 
                    WHERE shop_id = %s AND status != 'Выдан' AND is_archived = FALSE AND deleted_at IS NULL
                    ORDER BY 
                        CASE priority 
                            WHEN 'Высокий' THEN 1 
                            WHEN 'Обычный' THEN 2 
                            ELSE 3 
                        END,
                        created_at ASC
                """, (shop_id,))
                active_orders = cur.fetchall()
                
                cur.execute("""
                    SELECT * FROM orders 
                    WHERE shop_id = ? AND status = 'Выдан' AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 10
                """, (shop_id,)) if is_sqlite else cur.execute("""
                    SELECT * FROM orders 
                    WHERE shop_id = %s AND status = 'Выдан' AND deleted_at IS NULL
                    ORDER BY completed_at DESC NULLS LAST, created_at DESC
                    LIMIT 10
                """, (shop_id,))
                completed_orders = cur.fetchall()
                
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                        COUNT(*) FILTER (WHERE executor = ? AND status != 'Выдан') as my_active,
                        COUNT(*) FILTER (WHERE status = 'Выдан' AND DATE(completed_at) = DATE('now')) as completed_today
                    FROM orders 
                    WHERE shop_id = ? AND deleted_at IS NULL
                """, (user_name, shop_id)) if is_sqlite else cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                        COUNT(*) FILTER (WHERE executor = %s AND status != 'Выдан') as my_active,
                        COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today
                    FROM orders 
                    WHERE shop_id = %s AND deleted_at IS NULL
                """, (user_name, shop_id))
                shop_stats = cur.fetchone()
                
                orders_by_shop[shop_id] = {
                    'name': shop_name,
                    'active_orders': active_orders,
                    'completed_orders': completed_orders,
                    'stats': shop_stats
                }
            
            # Мои личные заказы
            cur.execute("""
                SELECT * FROM orders 
                WHERE executor = ? AND status != 'Выдан' AND is_archived = 0 AND deleted_at IS NULL
                ORDER BY 
                    CASE priority 
                        WHEN 'Высокий' THEN 1 
                        WHEN 'Обычный' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """, (user_name,)) if is_sqlite else cur.execute("""
                SELECT * FROM orders 
                WHERE executor = %s AND status != 'Выдан' AND is_archived = FALSE AND deleted_at IS NULL
                ORDER BY 
                    CASE priority 
                        WHEN 'Высокий' THEN 1 
                        WHEN 'Обычный' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """, (user_name,))
            my_orders = cur.fetchall()
            
            # Моя статистика
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                    COUNT(*) FILTER (WHERE status = 'Выдан' AND DATE(completed_at) = DATE('now')) as completed_today,
                    COUNT(*) FILTER (WHERE status = 'Новый') as new_orders
                FROM orders 
                WHERE executor = ? AND deleted_at IS NULL
            """, (user_name,)) if is_sqlite else cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                    COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today,
                    COUNT(*) FILTER (WHERE status = 'Новый') as new_orders
                FROM orders 
                WHERE executor = %s AND deleted_at IS NULL
            """, (user_name,))
            my_stats = cur.fetchone()
            
            # Задачи на сегодня
            cur.execute("""
                SELECT * FROM orders 
                WHERE executor = ? 
                AND status != 'Выдан' 
                AND is_archived = 0
                AND deleted_at IS NULL
                AND DATE(created_at) = DATE('now')
                ORDER BY 
                    CASE priority 
                        WHEN 'Высокий' THEN 1 
                        WHEN 'Обычный' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """, (user_name,)) if is_sqlite else cur.execute("""
                SELECT * FROM orders 
                WHERE executor = %s 
                AND status != 'Выдан' 
                AND is_archived = FALSE
                AND deleted_at IS NULL
                AND created_at::date = CURRENT_DATE
                ORDER BY 
                    CASE priority 
                        WHEN 'Высокий' THEN 1 
                        WHEN 'Обычный' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """, (user_name,))
            today_tasks = cur.fetchall()
            
            # Чат
            try:
                cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50;")
                chat_messages = cur.fetchall()
                chat_messages = list(reversed(chat_messages))
            except:
                chat_messages = []
        
        return render_template('employee_dashboard.html',
                             orders_by_shop=orders_by_shop,
                             my_orders=my_orders,
                             my_stats=my_stats,
                             today_tasks=today_tasks,
                             chat_messages=chat_messages,
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             now=datetime,
                             active_page='employee')
    except Exception as e:
        logger.exception("Ошибка кабинета сотрудника")
        flash('Ошибка загрузки данных', 'error')
        return render_template('employee_dashboard.html', 
                             orders_by_shop={},
                             my_orders=[], 
                             today_tasks=[],
                             chat_messages=[],
                             my_stats={'total': 0, 'active': 0, 'completed_today': 0, 'new_orders': 0},
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             now=datetime,
                             active_page='employee')

# ==========================================
# ЗАКАЗЫ
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
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            # Базовый запрос
            if is_sqlite:
                query = "SELECT * FROM orders WHERE shop_id = ? AND deleted_at IS NULL"
                count_query = "SELECT COUNT(*) FROM orders WHERE shop_id = ? AND deleted_at IS NULL"
            else:
                query = "SELECT * FROM orders WHERE shop_id = %s AND deleted_at IS NULL"
                count_query = "SELECT COUNT(*) FROM orders WHERE shop_id = %s AND deleted_at IS NULL"
            params = [shop_id]
            
            if not show_archived:
                query += " AND is_archived = 0" if is_sqlite else " AND is_archived = FALSE"
                count_query += " AND is_archived = 0" if is_sqlite else " AND is_archived = FALSE"
            
            if order_id_search and order_id_search.isdigit():
                query += " AND id = ?" if is_sqlite else " AND id = %s"
                count_query += " AND id = ?" if is_sqlite else " AND id = %s"
                params.append(int(order_id_search))
            
            if search:
                query += " AND (customer LIKE ? OR phone LIKE ? OR product LIKE ?)" if is_sqlite else " AND (customer ILIKE %s OR phone ILIKE %s OR product ILIKE %s)"
                count_query += " AND (customer LIKE ? OR phone LIKE ? OR product LIKE ?)" if is_sqlite else " AND (customer ILIKE %s OR phone ILIKE %s OR product ILIKE %s)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern, search_pattern])
            
            if status_filter:
                query += " AND status = ?" if is_sqlite else " AND status = %s"
                count_query += " AND status = ?" if is_sqlite else " AND status = %s"
                params.append(status_filter)
            
            if executor_filter:
                query += " AND executor = ?" if is_sqlite else " AND executor = %s"
                count_query += " AND executor = ?" if is_sqlite else " AND executor = %s"
                params.append(executor_filter)
            
            # Пагинация
            offset = (page - 1) * per_page
            query += " ORDER BY created_at DESC"
            if is_sqlite:
                query += f" LIMIT {per_page} OFFSET {offset};"
            else:
                query += f" LIMIT {per_page} OFFSET {offset};"
            
            # Счетчик
            cur.execute(count_query, params[:len(params) - (2 if offset else 0)])
            total_count = cur.fetchone()[0] if cur.fetchone() else 0
            
            # Получение заказов
            cur.execute(query, params[:len(params) - (2 if offset else 0)] if offset else params)
            orders = cur.fetchall()
            
            # Статусы для фильтра
            status_query = "SELECT DISTINCT status FROM orders WHERE shop_id = ? AND deleted_at IS NULL;" if is_sqlite else "SELECT DISTINCT status FROM orders WHERE shop_id = %s AND deleted_at IS NULL;"
            cur.execute(status_query, (shop_id,))
            statuses = [row[0] for row in cur.fetchall()]
            
            # Архив
            arch_query = "SELECT COUNT(*) FROM orders WHERE shop_id = ? AND is_archived = 1 AND deleted_at IS NULL;" if is_sqlite else "SELECT COUNT(*) FROM orders WHERE shop_id = %s AND is_archived = TRUE AND deleted_at IS NULL;"
            cur.execute(arch_query, (shop_id,))
            archived_count = cur.fetchone()[0] or 0
        
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
                             total_pages=(total_count + per_page - 1) // per_page if total_count > 0 else 1,
                             total_count=total_count,
                             active_page='orders')
    except Exception as e:
        logger.exception("Ошибка заказов")
        flash('Ошибка загрузки данных', 'error')
        return render_template('orders.html', orders=[], statuses=[], executors=[], employees=[], shops=Config.SHOPS, active_page='orders')

@app.route('/orders/create', methods=['GET'])
@login_required
def create_order_form():
    return render_template('create_order.html', shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='orders')

@app.route('/orders/add', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def add_order():
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        customer = request.form.get('customer', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product', '').strip()
        price = safe_float(request.form.get('price'))
        prepaid = safe_float(request.form.get('prepaid'))
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                                       priority, executor, status, comment, shop_id, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id;
                """, (customer, phone, address, product, price, prepaid, priority, executor, 
                      status, comment, shop_id, session.get('user_name')))
            else:
                cur.execute("""
                    INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                                       priority, executor, status, comment, shop_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (customer, phone, address, product, price, prepaid, priority, executor, 
                      status, comment, shop_id, session.get('user_name')))
            order_id = cur.fetchone()[0]
        
        flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка создания заказа")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['GET'])
@login_required
def edit_order_form(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = ? AND shop_id = ? AND deleted_at IS NULL;", (order_id, shop_id)) if is_sqlite else cur.execute("SELECT * FROM orders WHERE id = %s AND shop_id = %s AND deleted_at IS NULL;", (order_id, shop_id))
            order = cur.fetchone()
        
        if not order:
            flash('❌ Заказ не найден!', 'error')
            return redirect(url_for('orders_page'))
        
        return render_template('edit_order.html', order=order, shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='orders')
    except Exception as e:
        logger.exception("Ошибка загрузки заказа")
        flash('Ошибка загрузки заказа', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        customer = request.form.get('customer', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product', '').strip()
        price = safe_float(request.form.get('price'))
        prepaid = safe_float(request.form.get('prepaid'))
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    UPDATE orders 
                    SET customer = ?, phone = ?, address = ?, product = ?, 
                        price = ?, prepaid = ?, priority = ?, executor = ?, 
                        status = ?, comment = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND shop_id = ? AND deleted_at IS NULL
                    RETURNING id;
                """, (customer, phone, address, product, price, prepaid, priority, executor, 
                      status, comment, order_id, shop_id))
            else:
                cur.execute("""
                    UPDATE orders 
                    SET customer = %s, phone = %s, address = %s, product = %s, 
                        price = %s, prepaid = %s, priority = %s, executor = %s, 
                        status = %s, comment = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND shop_id = %s AND deleted_at IS NULL
                    RETURNING id;
                """, (customer, phone, address, product, price, prepaid, priority, executor, 
                      status, comment, order_id, shop_id))
            if cur.fetchone():
                flash(f'✅ Заказ #{order_id} успешно обновлен!', 'success')
            else:
                flash('❌ Заказ не найден или уже удален!', 'error')
        
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка редактирования")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/update', methods=['POST'])
@login_required
def update_order(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        status = request.form.get('status')
        executor = request.form.get('executor')
        employee_notes = request.form.get('employee_notes', '').strip()
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    UPDATE orders 
                    SET status = ?, executor = ?, employee_notes = ?,
                        completed_at = CASE WHEN ? = 'Выдан' THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND shop_id = ? AND deleted_at IS NULL;
                """, (status, executor, employee_notes, status, order_id, shop_id))
            else:
                cur.execute("""
                    UPDATE orders 
                    SET status = %s, executor = %s, employee_notes = %s,
                        completed_at = CASE WHEN %s = 'Выдан' THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND shop_id = %s AND deleted_at IS NULL;
                """, (status, executor, employee_notes, status, order_id, shop_id))
        
        flash(f'✅ Заказ #{order_id} обновлен!', 'success')
        return redirect(request.referrer or url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка обновления")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(request.referrer or url_for('orders_page'))

@app.route('/orders/<int:order_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_order(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE orders SET is_archived = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND shop_id = ? AND deleted_at IS NULL;", (order_id, shop_id)) if is_sqlite else cur.execute("UPDATE orders SET is_archived = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND shop_id = %s AND deleted_at IS NULL;", (order_id, shop_id))
        flash(f'📦 Заказ #{order_id} перемещен в архив!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка архивации")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/unarchive', methods=['POST'])
@login_required
@admin_required
def unarchive_order(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE orders SET is_archived = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND shop_id = ? AND deleted_at IS NULL;", (order_id, shop_id)) if is_sqlite else cur.execute("UPDATE orders SET is_archived = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND shop_id = %s AND deleted_at IS NULL;", (order_id, shop_id))
        flash(f'📤 Заказ #{order_id} восстановлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка восстановления")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/soft-delete', methods=['POST'])
@login_required
@admin_required
def soft_delete_order(order_id):
    try:
        shop_id = get_user_shop()
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE orders SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND shop_id = ? AND deleted_at IS NULL;", (order_id, shop_id)) if is_sqlite else cur.execute("UPDATE orders SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND shop_id = %s AND deleted_at IS NULL;", (order_id, shop_id))
        flash(f'🗑️ Заказ #{order_id} помечен как удаленный', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка удаления")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/complete', methods=['POST'])
@login_required
def complete_order(order_id):
    try:
        user_name = session.get('user_name')
        notes = request.form.get('notes', '')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    UPDATE orders 
                    SET status = 'Выдан', 
                        completed_at = CURRENT_TIMESTAMP,
                        employee_notes = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND executor = ? AND status != 'Выдан' AND deleted_at IS NULL
                """, (notes, order_id, user_name))
            else:
                cur.execute("""
                    UPDATE orders 
                    SET status = 'Выдан', 
                        completed_at = CURRENT_TIMESTAMP,
                        employee_notes = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND executor = %s AND status != 'Выдан' AND deleted_at IS NULL
                """, (notes, order_id, user_name))
        
        flash(f'✅ Заказ #{order_id} завершен!', 'success')
        return redirect(url_for('employee_dashboard'))
    except Exception as e:
        logger.exception("Ошибка завершения")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('employee_dashboard'))

# ==========================================
# КЛИЕНТЫ
# ==========================================

@app.route('/clients')
@login_required
def clients_page():
    try:
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    SELECT customer, phone, COUNT(*) as total_orders, 
                           SUM(price) as total_spent,
                           GROUP_CONCAT(DISTINCT shop_id) as shops
                    FROM orders
                    WHERE is_archived = 0 AND deleted_at IS NULL
                    GROUP BY customer, phone
                    ORDER BY total_spent DESC;
                """)
            else:
                cur.execute("""
                    SELECT customer, phone, COUNT(*) as total_orders, 
                           SUM(price) as total_spent,
                           STRING_AGG(DISTINCT shop_id, ', ') as shops
                    FROM orders
                    WHERE is_archived = FALSE AND deleted_at IS NULL
                    GROUP BY customer, phone
                    ORDER BY total_spent DESC;
                """)
            clients = cur.fetchall()
        
        return render_template('clients.html', clients=clients, shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='clients')
    except Exception as e:
        logger.exception("Ошибка клиентов")
        flash('Ошибка загрузки клиентов', 'error')
        return render_template('clients.html', clients=[], shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='clients')

# ==========================================
# ЧАТ
# ==========================================

@app.route('/chat')
@login_required
def chat_page():
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50;")
            chat_messages = cur.fetchall()
            chat_messages = list(reversed(chat_messages))
        
        return render_template('chat.html', chat_messages=chat_messages, employees=Config.EMPLOYEES, shops=Config.SHOPS, active_page='chat')
    except Exception as e:
        logger.exception("Ошибка чата")
        flash('Ошибка загрузки чата', 'error')
        return render_template('chat.html', chat_messages=[], employees=Config.EMPLOYEES, shops=Config.SHOPS, active_page='chat')

@app.route('/api/chat/messages', methods=['GET'])
@login_required
def get_chat_messages():
    try:
        limit = request.args.get('limit', 50, type=int)
        after = request.args.get('after', type=int)
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if after:
                cur.execute("SELECT * FROM chat_messages WHERE id > ? ORDER BY created_at DESC LIMIT ?;", (after, limit)) if is_sqlite else cur.execute("SELECT * FROM chat_messages WHERE id > %s ORDER BY created_at DESC LIMIT %s;", (after, limit))
            else:
                cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT ?;", (limit,)) if is_sqlite else cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT %s;", (limit,))
            messages = cur.fetchall()
            
            result = []
            for msg in messages:
                result.append({
                    'id': msg[0],
                    'user_id': msg[1],
                    'user_name': msg[2],
                    'message': msg[3],
                    'created_at': msg[4].isoformat() if hasattr(msg[4], 'isoformat') else str(msg[4])
                })
        
        return jsonify(result)
    except Exception as e:
        logger.exception("Ошибка API чата")
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({"error": "Сообщение не может быть пустым"}), 400
        
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    INSERT INTO chat_messages (user_id, user_name, message)
                    VALUES (?, ?, ?)
                    RETURNING id, created_at
                """, (user_id, user_name, message))
            else:
                cur.execute("""
                    INSERT INTO chat_messages (user_id, user_name, message)
                    VALUES (%s, %s, %s)
                    RETURNING id, created_at
                """, (user_id, user_name, message))
            result = cur.fetchone()
        
        return jsonify({
            "success": True,
            "id": result[0],
            "created_at": result[1].isoformat() if hasattr(result[1], 'isoformat') else str(result[1])
        })
    except Exception as e:
        logger.exception("Ошибка отправки сообщения")
        return jsonify({"error": str(e)}), 500

# ==========================================
# КАЛЕНДАРЬ
# ==========================================

@app.route('/calendar')
@login_required
def calendar_page():
    try:
        return render_template('calendar.html', shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='calendar')
    except Exception as e:
        logger.exception("Ошибка календаря")
        flash('Ошибка загрузки календаря', 'error')
        return render_template('calendar.html', shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='calendar')

@app.route('/api/calendar/events')
@login_required
def calendar_events_api():
    try:
        user_name = session.get('user_name')
        is_admin = session.get('is_admin', False)
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if is_admin:
                cur.execute("""
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE is_archived = 0 AND deleted_at IS NULL
                """ if is_sqlite else """
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE is_archived = FALSE AND deleted_at IS NULL
                """)
            else:
                cur.execute("""
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE executor = ? AND is_archived = 0 AND deleted_at IS NULL
                """, (user_name,)) if is_sqlite else cur.execute("""
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE executor = %s AND is_archived = FALSE AND deleted_at IS NULL
                """, (user_name,))
            orders = cur.fetchall()
        
        events = []
        status_colors = {
            'Новый': '#3498db',
            'В работе': '#f39c12',
            'Выдан': '#2ecc71'
        }
        
        for order in orders:
            created_at = order[5] if len(order) > 5 else None
            completed_at = order[6] if len(order) > 6 else None
            order_id = order[0]
            customer = order[1]
            product = order[2]
            status = order[3]
            priority = order[4]
            executor = order[7] if len(order) > 7 else 'Не назначен'
            
            if created_at:
                events.append({
                    'id': f"order_{order_id}",
                    'title': f"#{order_id} {customer[:20] if customer else ''}",
                    'start': created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                    'color': status_colors.get(status, '#95a5a6'),
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order_id,
                        'customer': customer,
                        'product': product,
                        'status': status,
                        'priority': priority,
                        'executor': executor
                    }
                })
            
            if status == 'Выдан' and completed_at:
                events.append({
                    'id': f"completed_{order_id}",
                    'title': f"✅ #{order_id} {customer[:15] if customer else ''}",
                    'start': completed_at.isoformat() if hasattr(completed_at, 'isoformat') else str(completed_at),
                    'color': '#2ecc71',
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order_id,
                        'status': 'Выдан'
                    }
                })
        
        return jsonify(events)
    except Exception as e:
        logger.exception("Ошибка API календаря")
        return jsonify([]), 500

# ==========================================
# УВЕДОМЛЕНИЯ
# ==========================================

@app.route('/notifications')
@login_required
def notifications_page():
    try:
        user_id = session.get('user_id')
        filter_type = request.args.get('type', 'all')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if is_sqlite:
                query = "SELECT * FROM notifications WHERE user_id = ?"
            else:
                query = "SELECT * FROM notifications WHERE user_id = %s"
            params = [user_id]
            
            if filter_type == 'unread':
                query += " AND is_read = 0 AND is_archived = 0" if is_sqlite else " AND is_read = FALSE AND is_archived = FALSE"
            elif filter_type == 'read':
                query += " AND is_read = 1 AND is_archived = 0" if is_sqlite else " AND is_read = TRUE AND is_archived = FALSE"
            elif filter_type == 'archived':
                query += " AND is_archived = 1" if is_sqlite else " AND is_archived = TRUE"
            
            query += " ORDER BY created_at DESC LIMIT 100"
            cur.execute(query, params)
            notifications = cur.fetchall()
            
            cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ?", (user_id,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s", (user_id,))
            total = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0 AND is_archived = 0", (user_id,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE", (user_id,))
            unread = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_archived = 1", (user_id,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_archived = TRUE", (user_id,))
            archived = cur.fetchone()[0] or 0
        
        return render_template('notifications.html',
                             notifications=notifications,
                             stats={'total': total, 'unread': unread, 'archived': archived},
                             filter_type=filter_type,
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             active_page='notifications')
    except Exception as e:
        logger.exception("Ошибка уведомлений")
        flash('Ошибка загрузки уведомлений', 'error')
        return render_template('notifications.html',
                             notifications=[],
                             stats={'total': 0, 'unread': 0, 'archived': 0},
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             active_page='notifications')

@app.route('/api/notifications/check')
@login_required
def check_notifications_api():
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            # Новые заказы
            cur.execute("SELECT COUNT(*) FROM orders WHERE executor = ? AND status = 'Новый' AND is_archived = 0 AND deleted_at IS NULL;", (user_name,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM orders WHERE executor = %s AND status = 'Новый' AND is_archived = FALSE AND deleted_at IS NULL;", (user_name,))
            new_orders = cur.fetchone()[0] or 0
            
            # Непрочитанные уведомления
            cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0 AND is_archived = 0;", (user_id,)) if is_sqlite else cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE;", (user_id,))
            unread = cur.fetchone()[0] or 0
        
        return jsonify({'new_orders': new_orders, 'unread': unread})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/latest')
@login_required
def get_latest_notifications():
    try:
        user_id = session.get('user_id')
        limit = request.args.get('limit', 5, type=int)
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM notifications WHERE user_id = ? AND is_archived = 0 ORDER BY created_at DESC LIMIT ?;", (user_id, limit)) if is_sqlite else cur.execute("SELECT * FROM notifications WHERE user_id = %s AND is_archived = FALSE ORDER BY created_at DESC LIMIT %s;", (user_id, limit))
            notifications = cur.fetchall()
            
            result = []
            for n in notifications:
                result.append({
                    'id': n[0],
                    'title': n[5],
                    'message': n[6],
                    'is_read': n[8] == 1 if is_sqlite else n[8],
                    'created_at': n[11].isoformat() if hasattr(n[11], 'isoformat') else str(n[11]),
                    'action_url': n[10] or '/notifications'
                })
        
        return jsonify(result)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    try:
        user_id = session.get('user_id')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE notifications SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?;", (notif_id, user_id)) if is_sqlite else cur.execute("UPDATE notifications SET is_read = TRUE, read_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s;", (notif_id, user_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    try:
        user_id = session.get('user_id')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE notifications SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND is_read = 0;", (user_id,)) if is_sqlite else cur.execute("UPDATE notifications SET is_read = TRUE, read_at = CURRENT_TIMESTAMP WHERE user_id = %s AND is_read = FALSE;", (user_id,))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/archive/<int:notif_id>', methods=['POST'])
@login_required
def archive_notification(notif_id):
    try:
        user_id = session.get('user_id')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE notifications SET is_archived = 1 WHERE id = ? AND user_id = ?;", (notif_id, user_id)) if is_sqlite else cur.execute("UPDATE notifications SET is_archived = TRUE WHERE id = %s AND user_id = %s;", (notif_id, user_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# ОНЛАЙН-СТАТУС
# ==========================================

@app.route('/api/online/update', methods=['POST'])
@login_required
def update_online_status():
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        
        with get_db_cursor() as cur:
            if is_sqlite:
                cur.execute("""
                    INSERT INTO user_sessions (user_id, user_name, last_seen, is_online)
                    VALUES (?, ?, CURRENT_TIMESTAMP, 1)
                    ON CONFLICT(user_id) DO UPDATE SET 
                        last_seen = CURRENT_TIMESTAMP,
                        is_online = 1,
                        user_name = excluded.user_name
                """, (user_id, user_name))
            else:
                cur.execute("""
                    INSERT INTO user_sessions (user_id, user_name, last_seen, is_online)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, TRUE)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        last_seen = CURRENT_TIMESTAMP,
                        is_online = TRUE,
                        user_name = EXCLUDED.user_name
                """, (user_id, user_name))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/online/users')
@login_required
def get_online_users():
    try:
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT user_id, user_name, last_seen,
                       CASE 
                           WHEN julianday('now') - julianday(last_seen) < 0.0014 THEN 1
                           ELSE 0
                       END as is_online
                FROM user_sessions
                WHERE julianday('now') - julianday(last_seen) < 0.0035
                ORDER BY user_name
            """) if is_sqlite else cur.execute("""
                SELECT 
                    user_id,
                    user_name,
                    last_seen,
                    CASE 
                        WHEN NOW() - last_seen < INTERVAL '2 minutes' THEN TRUE
                        ELSE FALSE
                    END as is_online
                FROM user_sessions
                WHERE NOW() - last_seen < INTERVAL '5 minutes'
                ORDER BY user_name
            """)
            users = cur.fetchall()
            
            result = []
            for u in users:
                result.append({
                    'user_id': u[0],
                    'user_name': u[1],
                    'is_online': bool(u[3]) if len(u) > 3 else False
                })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/online/leave', methods=['POST'])
@login_required
def leave_online():
    try:
        user_id = session.get('user_id')
        is_sqlite = Config.DATABASE_URL.startswith('sqlite://')
        with get_db_cursor() as cur:
            cur.execute("UPDATE user_sessions SET is_online = 0, last_seen = CURRENT_TIMESTAMP WHERE user_id = ?;", (user_id,)) if is_sqlite else cur.execute("UPDATE user_sessions SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP WHERE user_id = %s;", (user_id,))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# ЗАПУСК
# ==========================================

if __name__ == '__main__':
    # Инициализация БД при старте
    init_db()
    
    print("=" * 60)
    print("🎯 InTarget Brest Motors — CRM система")
    print("=" * 60)
    print(f"📍 База данных: {Config.DATABASE_URL}")
    print(f"🔑 Пароль администратора: admin123")
    print(f"🔑 Пароль сотрудников: 123456")
    print(f"🌐 Запуск на: http://localhost:{Config.PORT}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
