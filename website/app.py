import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response
from functools import wraps
import psycopg2
from psycopg2.extras import DictCursor
import secrets
from datetime import datetime, timedelta
import json

load_dotenv()

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    DATABASE_URL = os.environ.get('DATABASE_URL')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    SITE_NAME = 'InTarget Brest Motors'
    
    SHOPS = {
        'moskovskaya': '🏪 ул. Московская, 123',
        'kariernaya': '🏪 ул. Карьерная, 45'
    }
    
    EMPLOYEES = [
    {'id': 'pavel_ivanovich', 'name': 'Павел Иванович', 'password': 'pavel123'},
    {'id': 'pavel', 'name': 'Павел', 'password': 'pavel123'},
    {'id': 'dmitry', 'name': 'Дмитрий', 'password': 'dmitry123'},
    {'id': 'alexander', 'name': 'Александр', 'password': 'alexander123'}
]

if not Config.ADMIN_PASSWORD:
    raise ValueError("❌ ADMIN_PASSWORD не найден!")
if not Config.DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден!")

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_db_connection():
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        raise

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

def get_user_shop():
    return session.get('shop_id', 'moskovskaya')

def get_shop_name():
    shop_id = get_user_shop()
    return Config.SHOPS.get(shop_id, 'ул. Московская, 123')

def get_employees():
    return Config.EMPLOYEES

def get_employee_names():
    return [emp['name'] for emp in Config.EMPLOYEES]

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
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'admin')
        
        if login_type == 'admin':
            password = request.form.get('password')
            shop_id = request.form.get('shop_id', 'moskovskaya')
            
            if password == Config.ADMIN_PASSWORD:
                session['logged_in'] = True
                session['is_admin'] = True
                session['user_id'] = 'admin'
                session['user_name'] = 'Администратор'
                session['shop_id'] = shop_id
                session['shop_name'] = Config.SHOPS.get(shop_id, 'ул. Московская, 123')
                flash(f'✅ Добро пожаловать, Администратор!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('❌ Неверный пароль!', 'error')
        
        elif login_type == 'employee':
            employee_id = request.form.get('employee_id')
            password = request.form.get('password')
            
            employee = get_employee_by_id(employee_id)
            if employee and employee['password'] == password:
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
    
    return render_template('login.html', 
                         shops=Config.SHOPS,
                         employees=Config.EMPLOYEES)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

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
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        if shop_id == 'all':
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;")
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders;")
            total_orders, active_orders = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
            today_orders = cur.fetchone()[0]
        else:
            cur.execute("SELECT * FROM orders WHERE shop_id = %s ORDER BY created_at DESC LIMIT 10;", (shop_id,))
            orders = cur.fetchall()
            
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Выдан') FROM orders WHERE shop_id = %s;", (shop_id,))
            total_orders, active_orders = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND created_at::date = CURRENT_DATE;", (shop_id,))
            today_orders = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return render_template('dashboard.html',
                             orders=orders,
                             total_orders=total_orders or 0,
                             active_orders=active_orders or 0,
                             today_orders=today_orders or 0,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('dashboard.html', orders=[], shops=Config.SHOPS, employees=get_employees())

# ==========================================
# КАБИНЕТ СОТРУДНИКА
# ==========================================
@app.route('/employee')
@login_required
def employee_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('dashboard'))
    
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # 1. Мои заказы (активные)
        cur.execute("""
            SELECT * FROM orders 
            WHERE executor = %s AND status != 'Выдан' AND is_archived = FALSE
            ORDER BY 
                CASE priority 
                    WHEN 'Высокий' THEN 1 
                    WHEN 'Обычный' THEN 2 
                    ELSE 3 
                END,
                created_at ASC
        """, (user_name,))
        my_orders = cur.fetchall()
        
        # 2. Моя история заказов (завершенные)
        cur.execute("""
            SELECT * FROM orders 
            WHERE executor = %s AND status = 'Выдан'
            ORDER BY completed_at DESC NULLS LAST, created_at DESC
            LIMIT 20
        """, (user_name,))
        order_history = cur.fetchall()
        
        # 3. Задачи на сегодня
        today = datetime.now().date()
        cur.execute("""
            SELECT * FROM orders 
            WHERE executor = %s 
            AND status != 'Выдан' 
            AND is_archived = FALSE
            AND created_at::date = %s
            ORDER BY 
                CASE priority 
                    WHEN 'Высокий' THEN 1 
                    WHEN 'Обычный' THEN 2 
                    ELSE 3 
                END,
                created_at ASC
        """, (user_name, today))
        today_tasks = cur.fetchall()
        
        # 4. Статистика
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today
            FROM orders 
            WHERE executor = %s
        """, (user_name,))
        stats = cur.fetchone()
        
        # 5. Последние сообщения чата
        cur.execute("""
            SELECT * FROM chat_messages 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
        chat_messages = cur.fetchall()
        chat_messages = list(reversed(chat_messages))  # В обратном порядке для отображения
        
        # 6. Непрочитанные уведомления (для чата)
        cur.execute("""
            SELECT COUNT(*) FROM chat_messages 
            WHERE created_at > (SELECT COALESCE(MAX(last_read), CURRENT_TIMESTAMP - INTERVAL '1 day') 
                               FROM user_read_status WHERE user_id = %s)
        """, (user_id,))
        unread_chat = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return render_template('employee_dashboard.html',
                             my_orders=my_orders,
                             order_history=order_history,
                             today_tasks=today_tasks,
                             stats=stats,
                             chat_messages=chat_messages,
                             unread_chat=unread_chat,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка кабинета сотрудника: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('employee_dashboard.html', 
                             my_orders=[], 
                             order_history=[], 
                             today_tasks=[],
                             chat_messages=[])

# ==========================================
# УПРАВЛЕНИЕ ЗАКАЗАМИ
# ==========================================
@app.route('/orders')
@login_required
def orders_page():
    try:
        shop_id = get_user_shop()
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        executor_filter = request.args.get('executor', '')
        show_archived = request.args.get('show_archived', 'false') == 'true'
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        query = "SELECT * FROM orders WHERE shop_id = %s"
        params = [shop_id]
        
        if not show_archived:
            query += " AND is_archived = FALSE"
        
        if search:
            query += " AND (customer ILIKE %s OR phone ILIKE %s OR product ILIKE %s)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if status_filter:
            query += " AND status = %s"
            params.append(status_filter)
        
        if executor_filter:
            query += " AND executor = %s"
            params.append(executor_filter)
        
        query += " ORDER BY created_at DESC;"
        
        cur.execute(query, params)
        orders = cur.fetchall()
        
        cur.execute("SELECT DISTINCT status FROM orders WHERE shop_id = %s;", (shop_id,))
        statuses = [row['status'] for row in cur.fetchall()]
        
        executors = get_employee_names()
        
        cur.execute("SELECT COUNT(*) FROM orders WHERE shop_id = %s AND is_archived = TRUE;", (shop_id,))
        archived_count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return render_template('orders.html',
                             orders=orders,
                             all_orders=orders,
                             statuses=statuses,
                             executors=executors,
                             employees=get_employees(),
                             search=search,
                             current_status=status_filter,
                             current_executor=executor_filter,
                             show_archived=show_archived,
                             archived_count=archived_count,
                             shops=Config.SHOPS)
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('orders.html', orders=[], all_orders=[], statuses=[], executors=[], employees=[])

# --- Добавление заказа ---
@app.route('/orders/add', methods=['POST'])
@login_required
def add_order():
    try:
        shop_id = get_user_shop()
        customer = request.form.get('customer')
        phone = request.form.get('phone')
        address = request.form.get('address')
        product = request.form.get('product')
        price = safe_float(request.form.get('price'))
        prepaid = safe_float(request.form.get('prepaid'))
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment')
        
        conn = get_db_connection()
        cur = conn.cursor()
        query = """
            INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                               priority, executor, status, comment, shop_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        cur.execute(query, (customer, phone, address, product, price, prepaid, 
                           priority, executor, status, comment, shop_id))
        order_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# --- Обновление статуса заказа ---
@app.route('/orders/<int:order_id>/update', methods=['POST'])
@login_required
def update_order(order_id):
    try:
        shop_id = get_user_shop()
        status = request.form.get('status')
        executor = request.form.get('executor')
        employee_notes = request.form.get('employee_notes', '')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем доступ
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
        # Если статус 'Выдан' - записываем время завершения
        completed_at = 'CURRENT_TIMESTAMP' if status == 'Выдан' else 'NULL'
        
        query = f"""
            UPDATE orders 
            SET status = %s, 
                executor = %s, 
                employee_notes = %s,
                completed_at = {completed_at},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND shop_id = %s;
        """
        cur.execute(query, (status, executor, employee_notes, order_id, shop_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'✅ Заказ #{order_id} обновлен!', 'success')
        return redirect(request.referrer or url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(request.referrer or url_for('orders_page'))

# --- Завершение заказа (для сотрудников) ---
@app.route('/orders/<int:order_id>/complete', methods=['POST'])
@login_required
def complete_order(order_id):
    try:
        user_name = session.get('user_name')
        notes = request.form.get('notes', '')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем, что заказ принадлежит сотруднику
        cur.execute("""
            SELECT id FROM orders 
            WHERE id = %s AND executor = %s AND status != 'Выдан'
        """, (order_id, user_name))
        
        if not cur.fetchone():
            flash('❌ Заказ не найден или уже завершен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('employee_dashboard'))
        
        cur.execute("""
            UPDATE orders 
            SET status = 'Выдан', 
                completed_at = CURRENT_TIMESTAMP,
                employee_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (notes, order_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'✅ Заказ #{order_id} завершен!', 'success')
        return redirect(url_for('employee_dashboard'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('employee_dashboard'))

# --- Архивация ---
@app.route('/orders/<int:order_id>/archive', methods=['POST'])
@login_required
def archive_order(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders 
            SET is_archived = TRUE, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND shop_id = %s;
        """, (order_id, shop_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'📦 Заказ #{order_id} перемещен в архив!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# --- Восстановление из архива ---
@app.route('/orders/<int:order_id>/unarchive', methods=['POST'])
@login_required
def unarchive_order(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
        cur.execute("""
            UPDATE orders 
            SET is_archived = FALSE, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND shop_id = %s;
        """, (order_id, shop_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'📤 Заказ #{order_id} восстановлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# --- Удаление ---
@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
        cur.execute("DELETE FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'🗑️ Заказ #{order_id} удален!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# КЛИЕНТЫ (ОБЩАЯ БАЗА)
# ==========================================
@app.route('/clients')
@login_required
def clients_page():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
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
        cur.close()
        conn.close()
        
        return render_template('clients.html', 
                             clients=clients,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки клиентов', 'error')
        return render_template('clients.html', clients=[])

# ==========================================
# ВНУТРЕННИЙ ЧАТ (API)
# ==========================================
@app.route('/api/chat/messages', methods=['GET'])
@login_required
def get_chat_messages():
    try:
        limit = request.args.get('limit', 50, type=int)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT * FROM chat_messages 
            ORDER BY created_at DESC 
            LIMIT %s
        """, (limit,))
        messages = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify([dict(msg) for msg in messages])
    except Exception as e:
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
        user_role = session.get('user_role', 'Сотрудник')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_messages (user_id, user_name, user_role, message)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
        """, (user_id, user_name, user_role, message))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "id": result[0],
            "created_at": result[1].isoformat()
        })
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# API СТАТИСТИКА
# ==========================================
@app.route('/api/stats/employee')
@login_required
def api_employee_stats():
    try:
        user_name = session.get('user_name')
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute("""
            SELECT 
                COUNT(*) as total_orders,
                COUNT(*) FILTER (WHERE status = 'Выдан') as completed_orders,
                COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today,
                COUNT(*) FILTER (WHERE status != 'Выдан') as active_orders,
                AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/3600) as avg_hours
            FROM orders 
            WHERE executor = %s
        """, (user_name,))
        
        stats = cur.fetchone()
        cur.close()
        conn.close()
        
        return jsonify(dict(stats))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
