import os
import logging
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from flask_session import Session

load_dotenv()

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'
    
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_sessions'
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    
    SHOPS = {
        'moskovskaya': '🏪 ул. Московская, 123',
        'kariernaya': '🏪 ул. Карьерная, 45'
    }
    
    EMPLOYEES = [
        {'id': 'pavel_ivanovich', 'name': 'Павел Иванович'},
        {'id': 'pavel', 'name': 'Павел'},
        {'id': 'dmitry', 'name': 'Дмитрий'},
        {'id': 'alexander', 'name': 'Александр'}
    ]

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
Session(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('brest_motors')

# ==========================================
# РАБОТА С БАЗОЙ ДАННЫХ
# ==========================================

@contextmanager
def get_db_cursor():
    """Контекстный менеджер для работы с БД"""
    conn = psycopg2.connect(Config.DATABASE_URL)
    cur = conn.cursor(cursor_factory=DictCursor)
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
    """Инициализация таблиц (если не существуют)"""
    try:
        with get_db_cursor() as cur:
            # Таблица заказов (добавлена колонка updated_at)
            cur.execute("""
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
                    status TEXT DEFAULT 'Новый',
                    comment TEXT,
                    shop_id TEXT DEFAULT 'moskovskaya',
                    is_archived BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            # Таблица чата
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("✅ База данных инициализирована")
            
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

# Инициализируем БД при запуске модуля
init_db()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

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

def get_employee_by_id(emp_id):
    for emp in Config.EMPLOYEES:
        if emp['id'] == emp_id:
            return emp
    return None

# ==========================================
# МАРШРУТЫ АВТОРИЗАЦИИ
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')
        
        if login_type == 'admin':
            shop_id = request.form.get('shop_id', 'moskovskaya')
            session.permanent = True
            session['logged_in'] = True
            session['is_admin'] = True
            session['user_id'] = 'admin'
            session['user_name'] = 'Администратор'
            session['shop_id'] = shop_id
            session['shop_name'] = Config.SHOPS.get(shop_id, 'ул. Московская, 123')
            flash('✅ Добро пожаловать, Администратор!', 'success')
            return redirect(url_for('dashboard'))
        
        elif login_type == 'employee':
            employee_id = request.form.get('employee_id')
            employee = get_employee_by_id(employee_id)
            if employee:
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
                flash('❌ Сотрудник не найден!', 'error')
    
    return render_template('login.html', shops=Config.SHOPS, employees=Config.EMPLOYEES)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/force-login')
def force_login():
    session['logged_in'] = True
    session['is_admin'] = True
    session['user_id'] = 'admin'
    session['user_name'] = 'Администратор'
    session['shop_id'] = 'moskovskaya'
    session['shop_name'] = '🏪 ул. Московская, 123'
    flash('✅ Вход выполнен', 'success')
    return redirect(url_for('dashboard'))

@app.route('/force-employee/<emp_id>')
def force_employee(emp_id):
    employee = get_employee_by_id(emp_id)
    if employee:
        session['logged_in'] = True
        session['is_admin'] = False
        session['user_id'] = employee['id']
        session['user_name'] = employee['name']
        session['shop_id'] = 'all'
        session['shop_name'] = 'Все магазины'
        flash(f'✅ Вход как {employee["name"]}', 'success')
        return redirect(url_for('employee_dashboard'))
    flash('❌ Сотрудник не найден', 'error')
    return redirect(url_for('login'))

# ==========================================
# ДАШБОРД
# ==========================================

@app.route('/')
@login_required
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('employee_dashboard'))
    
    try:
        shop_id = session.get('shop_id', 'moskovskaya')
        
        with get_db_cursor() as cur:
            if shop_id == 'all':
                cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50;")
            else:
                cur.execute("SELECT * FROM orders WHERE shop_id = %s ORDER BY created_at DESC LIMIT 50;", (shop_id,))
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*) FROM orders;")
            total_orders = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE status != 'Выдан';")
            active_orders = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
            today_orders = cur.fetchone()[0] or 0
            
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
        logger.exception("Ошибка дашборда")
        flash(f'Ошибка загрузки данных: {e}', 'error')
        return render_template('dashboard.html', orders=[], shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='dashboard', datetime=datetime)

# ==========================================
# СПИСОК ЗАКАЗОВ
# ==========================================

@app.route('/orders')
@login_required
def orders_page():
    try:
        shop_id = session.get('shop_id', 'moskovskaya')
        show_archived = request.args.get('show_archived', 'false') == 'true'
        
        with get_db_cursor() as cur:
            if shop_id == 'all':
                if show_archived:
                    cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
                else:
                    cur.execute("SELECT * FROM orders WHERE is_archived = FALSE ORDER BY created_at DESC;")
                
                cur.execute("SELECT DISTINCT status FROM orders;")
                statuses = [row[0] for row in cur.fetchall()]
                
                cur.execute("SELECT COUNT(*) FROM orders WHERE is_archived = TRUE;")
                archived_count = cur.fetchone()[0] or 0
            else:
                if show_archived:
                    cur.execute("SELECT * FROM orders WHERE shop_id = %s ORDER BY created_at DESC;", (shop_id,))
                else:
                    cur.execute("SELECT * FROM orders WHERE shop_id = %s AND is_archived = FALSE ORDER BY created_at DESC;", (shop_id,))
                
                cur.execute("SELECT DISTINCT status FROM orders WHERE shop_id = %s;", (shop_id,))
                statuses = [row[0] for row in cur.fetchall()]
                
                cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND is_archived = TRUE;", (shop_id,))
                archived_count = cur.fetchone()[0] or 0
                
            orders = cur.fetchall()
        
        return render_template('orders.html',
                             orders=orders,
                             statuses=statuses,
                             executors=['Павел Иванович', 'Павел', 'Дмитрий', 'Александр'],
                             employees=Config.EMPLOYEES,
                             search='',
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
        logger.exception("Ошибка заказов")
        flash(f'Ошибка загрузки заказов: {e}', 'error')
        return render_template('orders.html', orders=[], statuses=[], executors=[], employees=[], shops=Config.SHOPS, active_page='orders')

# ==========================================
# СОЗДАНИЕ ЗАКАЗА
# ==========================================

@app.route('/orders/create', methods=['GET'])
@login_required
def create_order_form():
    return render_template('create_order.html', shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='orders')

@app.route('/orders/add', methods=['POST'])
@login_required
def add_order():
    try:
        shop_id = session.get('shop_id', 'moskovskaya')
        customer = request.form.get('customer', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product', '').strip()
        price = float(request.form.get('price', 0) or 0)
        prepaid = float(request.form.get('prepaid', 0) or 0)
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                                   priority, executor, status, comment, shop_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (customer, phone, address, product, price, prepaid, priority, executor, 
                  status, comment, shop_id))
            order_id = cur.fetchone()[0]
        
        flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка создания заказа")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# РЕДАКТИРОВАНИЕ ЗАКАЗА
# ==========================================

@app.route('/orders/<int:order_id>/edit', methods=['GET'])
@login_required
def edit_order_form(order_id):
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s;", (order_id,))
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
        customer = request.form.get('customer', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        product = request.form.get('product', '').strip()
        price = float(request.form.get('price', 0) or 0)
        prepaid = float(request.form.get('prepaid', 0) or 0)
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment', '').strip()
        
        completed_at = CURRENT_TIMESTAMP if status == 'Выдан' else None
        
        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE orders 
                SET customer = %s, phone = %s, address = %s, product = %s, 
                    price = %s, prepaid = %s, priority = %s, executor = %s, 
                    status = %s, comment = %s, updated_at = CURRENT_TIMESTAMP,
                    completed_at = CASE WHEN %s = 'Выдан' THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = %s
            """, (customer, phone, address, product, price, prepaid, priority, executor, 
                  status, comment, status, order_id))
        
        flash(f'✅ Заказ #{order_id} успешно обновлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка редактирования")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# АРХИВАЦИЯ / ВОССТАНОВЛЕНИЕ
# ==========================================

@app.route('/orders/<int:order_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_order(order_id):
    try:
        with get_db_cursor() as cur:
            cur.execute("UPDATE orders SET is_archived = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (order_id,))
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
        with get_db_cursor() as cur:
            cur.execute("UPDATE orders SET is_archived = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (order_id,))
        flash(f'📤 Заказ #{order_id} восстановлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        logger.exception("Ошибка восстановления")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# КЛИЕНТЫ
# ==========================================

@app.route('/clients')
@login_required
def clients_page():
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT customer, phone, COUNT(*) as total_orders, 
                       SUM(price) as total_spent,
                       STRING_AGG(DISTINCT shop_id, ', ') as shops
                FROM orders
                WHERE is_archived = FALSE
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
# КАБИНЕТ СОТРУДНИКА
# ==========================================

@app.route('/employee')
@login_required
def employee_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('dashboard'))
    
    try:
        user_name = session.get('user_name')
        
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT * FROM orders 
                WHERE executor = %s AND status != 'Выдан' AND is_archived = FALSE
                ORDER BY created_at ASC
            """, (user_name,))
            my_orders = cur.fetchall()
            
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                    COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today,
                    COUNT(*) FILTER (WHERE status = 'Новый') as new_orders
                FROM orders 
                WHERE executor = %s
            """, (user_name,))
            my_stats = cur.fetchone()
            
            orders_by_shop = {}
            for shop_id, shop_name in Config.SHOPS.items():
                cur.execute("""
                    SELECT * FROM orders 
                    WHERE shop_id = %s AND status != 'Выдан' AND is_archived = FALSE
                    ORDER BY created_at ASC
                """, (shop_id,))
                active_orders = cur.fetchall()
                
                orders_by_shop[shop_id] = {
                    'name': shop_name,
                    'active_orders': active_orders,
                    'stats': {'active': len(active_orders), 'my_active': 0}
                }
        
        return render_template('employee_dashboard.html',
                             orders_by_shop=orders_by_shop,
                             my_orders=my_orders,
                             my_stats=my_stats,
                             today_tasks=[],
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
                             my_stats={'total': 0, 'active': 0, 'completed_today': 0, 'new_orders': 0},
                             shops=Config.SHOPS,
                             employees=Config.EMPLOYEES,
                             now=datetime,
                             active_page='employee')

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
        
        with get_db_cursor() as cur:
            if after:
                cur.execute("SELECT * FROM chat_messages WHERE id > %s ORDER BY created_at DESC LIMIT %s;", (after, limit))
            else:
                cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT %s;", (limit,))
            messages = cur.fetchall()
            
            result = []
            for msg in messages:
                result.append({
                    'id': msg['id'],
                    'user_name': msg['user_name'],
                    'message': msg['message'],
                    'created_at': msg['created_at'].isoformat()
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
        
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO chat_messages (user_id, user_name, message)
                VALUES (%s, %s, %s)
                RETURNING id, created_at
            """, (user_id, user_name, message))
            result = cur.fetchone()
        
        return jsonify({
            "success": True,
            "id": result[0],
            "created_at": result[1].isoformat()
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
    return render_template('calendar.html', shops=Config.SHOPS, employees=Config.EMPLOYEES, active_page='calendar')

@app.route('/api/calendar/events')
@login_required
def calendar_events_api():
    try:
        user_name = session.get('user_name')
        is_admin = session.get('is_admin', False)
        
        with get_db_cursor() as cur:
            if is_admin:
                cur.execute("""
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE is_archived = FALSE
                """)
            else:
                cur.execute("""
                    SELECT id, customer, product, status, priority, created_at, 
                           completed_at, executor, shop_id
                    FROM orders
                    WHERE executor = %s AND is_archived = FALSE
                """, (user_name,))
            orders = cur.fetchall()
        
        events = []
        status_colors = {
            'Новый': '#3498db',
            'В работе': '#f39c12',
            'Выдан': '#2ecc71'
        }
        
        for order in orders:
            if order['created_at']:
                events.append({
                    'id': f"order_{order['id']}",
                    'title': f"#{order['id']} {order['customer'][:20]}",
                    'start': order['created_at'].isoformat(),
                    'color': status_colors.get(order['status'], '#95a5a6'),
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order['id'],
                        'customer': order['customer'],
                        'product': order['product'],
                        'status': order['status'],
                        'priority': order['priority'],
                        'executor': order['executor']
                    }
                })
            
            if order['status'] == 'Выдан' and order['completed_at']:
                events.append({
                    'id': f"completed_{order['id']}",
                    'title': f"✅ #{order['id']} {order['customer'][:15]}",
                    'start': order['completed_at'].isoformat(),
                    'color': '#2ecc71',
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order['id'],
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
    return render_template('notifications.html', 
                         notifications=[],
                         stats={'total': 0, 'unread': 0, 'archived': 0},
                         shops=Config.SHOPS,
                         employees=Config.EMPLOYEES,
                         active_page='notifications')

@app.route('/api/notifications/check')
@login_required
def check_notifications_api():
    return jsonify({'new_orders': 0, 'unread': 0})

@app.route('/api/notifications/latest')
@login_required
def get_latest_notifications():
    return jsonify([])

# ==========================================
# ЗАПУСК
# ==========================================

if __name__ == '__main__':
    print("=" * 60)
    print("🎯 InTarget Brest Motors — CRM система")
    print("=" * 60)
    print(f"📍 База данных: {Config.DATABASE_URL}")
    print("🔑 Вход с ЛЮБЫМ паролем (временный режим)")
    print(f"🌐 Запуск на: http://localhost:{Config.PORT}")
    print("=" * 60)
    print("⚡ Быстрый вход: /force-login")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
