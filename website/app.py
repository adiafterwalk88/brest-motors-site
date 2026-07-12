import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
import psycopg2
from psycopg2.extras import DictCursor
import secrets
from datetime import datetime

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

def check_new_orders(user_name):
    """Проверяет наличие новых заказов для сотрудника"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM orders 
            WHERE executor = %s AND status = 'Новый' AND is_archived = FALSE
        """, (user_name,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"Ошибка проверки новых заказов: {e}")
        return 0

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
        print(f"Ошибка дашборда: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('dashboard.html', 
                             orders=[], 
                             shops=Config.SHOPS, 
                             employees=get_employees())

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
        
        # Получаем заказы по магазинам
        orders_by_shop = {}
        for shop_id, shop_name in Config.SHOPS.items():
            # Активные заказы для магазина
            cur.execute("""
                SELECT * FROM orders 
                WHERE shop_id = %s AND status != 'Выдан' AND is_archived = FALSE
                ORDER BY 
                    CASE priority 
                        WHEN 'Высокий' THEN 1 
                        WHEN 'Обычный' THEN 2 
                        ELSE 3 
                    END,
                    created_at ASC
            """, (shop_id,))
            active_orders = cur.fetchall()
            
            # Выполненные заказы для магазина
            cur.execute("""
                SELECT * FROM orders 
                WHERE shop_id = %s AND status = 'Выдан'
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
                LIMIT 10
            """, (shop_id,))
            completed_orders = cur.fetchall()
            
            # Статистика по магазину
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status != 'Выдан') as active,
                    COUNT(*) FILTER (WHERE executor = %s AND status != 'Выдан') as my_active,
                    COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) as completed_today
                FROM orders 
                WHERE shop_id = %s
            """, (user_name, shop_id))
            shop_stats = cur.fetchone()
            
            orders_by_shop[shop_id] = {
                'name': shop_name,
                'active_orders': active_orders,
                'completed_orders': completed_orders,
                'stats': shop_stats
            }
        
        # Мои личные заказы (все магазины)
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
        
        # Моя статистика
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
        
        # Задачи на сегодня
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
        
        # Чат
        try:
            cur.execute("""
                SELECT * FROM chat_messages 
                ORDER BY created_at DESC 
                LIMIT 50
            """)
            chat_messages = cur.fetchall()
            chat_messages = list(reversed(chat_messages))
            
            cur.execute("""
                SELECT COUNT(*) FROM chat_messages 
                WHERE created_at > NOW() - INTERVAL '1 hour'
            """)
            unread_chat = cur.fetchone()[0]
        except Exception as e:
            print(f"Ошибка загрузки чата: {e}")
            chat_messages = []
            unread_chat = 0
        
        cur.close()
        conn.close()
        
        return render_template('employee_dashboard.html',
                             orders_by_shop=orders_by_shop,
                             my_orders=my_orders,
                             my_stats=my_stats,
                             today_tasks=today_tasks,
                             chat_messages=chat_messages,
                             unread_chat=unread_chat,
                             shops=Config.SHOPS,
                             employees=get_employees(),
                             now=datetime.now())
    except Exception as e:
        print(f"Ошибка кабинета: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('employee_dashboard.html', 
                             orders_by_shop={},
                             my_orders=[], 
                             today_tasks=[],
                             chat_messages=[],
                             my_stats={'total': 0, 'active': 0, 'completed_today': 0, 'new_orders': 0},
                             unread_chat=0,
                             shops=Config.SHOPS,
                             employees=get_employees(),
                             now=datetime.now())

# ==========================================
# СОЗДАНИЕ ЗАКАЗА СОТРУДНИКОМ
# ==========================================
@app.route('/employee/orders/create', methods=['GET', 'POST'])
@login_required
def employee_create_order():
    """Создание заказа из кабинета сотрудника"""
    if session.get('is_admin'):
        return redirect(url_for('create_order_form'))
    
    if request.method == 'POST':
        try:
            customer = request.form.get('customer')
            phone = request.form.get('phone')
            address = request.form.get('address')
            product = request.form.get('product')
            price = safe_float(request.form.get('price'))
            prepaid = safe_float(request.form.get('prepaid'))
            priority = request.form.get('priority') or 'Обычный'
            comment = request.form.get('comment')
            shop_id = request.form.get('shop_id')
            
            # Сотрудник автоматически назначается исполнителем
            executor = session.get('user_name')
            status = 'Новый'
            
            # Если магазин не выбран, используем первый доступный
            if not shop_id or shop_id == 'all':
                shop_id = list(Config.SHOPS.keys())[0]
            
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
            
            flash(f'✅ Заказ #{order_id} успешно создан в магазине {Config.SHOPS.get(shop_id, shop_id)}! Вы назначены исполнителем.', 'success')
            return redirect(url_for('employee_dashboard'))
        except Exception as e:
            print(f"Ошибка создания заказа сотрудником: {e}")
            flash(f'❌ Ошибка: {e}', 'error')
            return redirect(url_for('employee_create_order'))
    
    return render_template('employee_create_order.html',
                         shops=Config.SHOPS,
                         employees=get_employees(),
                         user_name=session.get('user_name'))

# ==========================================
# РЕДАКТИРОВАНИЕ ЗАКАЗА СОТРУДНИКОМ
# ==========================================
@app.route('/employee/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit_order(order_id):
    """Редактирование заказа сотрудником (только если он исполнитель)"""
    if session.get('is_admin'):
        return redirect(url_for('edit_order_form', order_id=order_id))
    
    user_name = session.get('user_name')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Проверяем, что сотрудник является исполнителем этого заказа
        cur.execute("""
            SELECT * FROM orders 
            WHERE id = %s AND executor = %s AND status != 'Выдан'
        """, (order_id, user_name))
        order = cur.fetchone()
        
        if not order:
            flash('❌ Вы не можете редактировать этот заказ! Возможно, он уже завершен или назначен другому сотруднику.', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('employee_dashboard'))
        
        if request.method == 'POST':
            customer = request.form.get('customer')
            phone = request.form.get('phone')
            address = request.form.get('address')
            product = request.form.get('product')
            price = safe_float(request.form.get('price'))
            prepaid = safe_float(request.form.get('prepaid'))
            priority = request.form.get('priority') or 'Обычный'
            status = request.form.get('status') or order['status']
            comment = request.form.get('comment')
            
            # Исполнитель не меняется
            query = """
                UPDATE orders 
                SET customer = %s, phone = %s, address = %s, product = %s, 
                    price = %s, prepaid = %s, priority = %s, status = %s, 
                    comment = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND executor = %s AND status != 'Выдан'
                RETURNING id;
            """
            cur.execute(query, (customer, phone, address, product, price, prepaid, 
                               priority, status, comment, order_id, user_name))
            
            if cur.fetchone():
                conn.commit()
                flash(f'✅ Заказ #{order_id} успешно обновлен!', 'success')
            else:
                flash('❌ Ошибка обновления заказа', 'error')
            
            cur.close()
            conn.close()
            return redirect(url_for('employee_dashboard'))
        
        cur.close()
        conn.close()
        
        return render_template('employee_edit_order.html',
                             order=order,
                             user_name=user_name,
                             shops=Config.SHOPS)
                             
    except Exception as e:
        print(f"Ошибка редактирования заказа сотрудником: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('employee_dashboard'))

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
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        query = "SELECT * FROM orders WHERE shop_id = %s"
        params = [shop_id]
        
        if not show_archived:
            query += " AND is_archived = FALSE"
        
        if order_id_search and order_id_search.isdigit():
            query += " AND id = %s"
            params.append(int(order_id_search))
        
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
                             order_id_search=order_id_search,
                             current_status=status_filter,
                             current_executor=executor_filter,
                             show_archived=show_archived,
                             archived_count=archived_count,
                             shops=Config.SHOPS)
    except Exception as e:
        print(f"Ошибка заказов: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('orders.html', 
                             orders=[], 
                             all_orders=[], 
                             statuses=[], 
                             executors=[],
                             employees=[],
                             shops=Config.SHOPS)

@app.route('/orders/create', methods=['GET'])
@login_required
def create_order_form():
    """Страница создания нового заказа"""
    try:
        return render_template('create_order.html',
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки формы', 'error')
        return redirect(url_for('orders_page'))

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
        print(f"Ошибка создания: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['GET'])
@login_required
def edit_order_form(order_id):
    """Страница редактирования заказа"""
    try:
        shop_id = get_user_shop()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute("SELECT * FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        order = cur.fetchone()
        cur.close()
        conn.close()
        
        if not order:
            flash('❌ Заказ не найден!', 'error')
            return redirect(url_for('orders_page'))
        
        return render_template('edit_order.html',
                             order=order,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка: {e}")
        flash('Ошибка загрузки заказа', 'error')
        return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    """Сохранение изменений заказа"""
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
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
        query = """
            UPDATE orders 
            SET customer = %s, 
                phone = %s, 
                address = %s, 
                product = %s, 
                price = %s, 
                prepaid = %s, 
                priority = %s, 
                executor = %s, 
                status = %s, 
                comment = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND shop_id = %s
            RETURNING id;
        """
        cur.execute(query, (customer, phone, address, product, price, prepaid, 
                           priority, executor, status, comment, order_id, shop_id))
        conn.commit()
        cur.close()
        conn.close()
        
        flash(f'✅ Заказ #{order_id} успешно обновлен!', 'success')
        return redirect(url_for('orders_page'))
    except Exception as e:
        print(f"Ошибка редактирования: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

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
        
        cur.execute("SELECT id FROM orders WHERE id = %s AND shop_id = %s;", (order_id, shop_id))
        if not cur.fetchone():
            flash('❌ Доступ запрещен!', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('orders_page'))
        
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
        print(f"Ошибка обновления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(request.referrer or url_for('orders_page'))

@app.route('/orders/<int:order_id>/complete', methods=['POST'])
@login_required
def complete_order(order_id):
    try:
        user_name = session.get('user_name')
        notes = request.form.get('notes', '')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
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
        print(f"Ошибка завершения: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('employee_dashboard'))

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
        print(f"Ошибка архивации: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

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
        print(f"Ошибка восстановления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

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
        print(f"Ошибка удаления: {e}")
        flash(f'❌ Ошибка: {e}', 'error')
        return redirect(url_for('orders_page'))

# ==========================================
# API УВЕДОМЛЕНИЙ
# ==========================================
@app.route('/api/notifications/check')
@login_required
def check_notifications_api():
    """API для проверки новых заказов"""
    try:
        user_name = session.get('user_name')
        count = check_new_orders(user_name)
        return jsonify({'new_orders': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# КЛИЕНТЫ
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
        print(f"Ошибка клиентов: {e}")
        flash('Ошибка загрузки клиентов', 'error')
        return render_template('clients.html', 
                             clients=[],
                             shops=Config.SHOPS,
                             employees=get_employees())

# ==========================================
# API ЧАТА
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
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_messages (user_id, user_name, message)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
        """, (user_id, user_name, message))
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
        print(f"Ошибка чата: {e}")
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
# НОВЫЕ МАРШРУТЫ - УВЕДОМЛЕНИЯ, ЧАТ, КАЛЕНДАРЬ
# ==========================================

# ------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ УВЕДОМЛЕНИЙ
# ------------------------------------------

def create_notification(user_id, user_name, title, message, order_id=None, 
                        notification_type='reminder', priority='Обычный', 
                        scheduled_for=None, action_url=None, metadata=None):
    """Создание уведомления"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO notifications 
            (user_id, user_name, order_id, notification_type, title, message, 
             priority, scheduled_for, action_url, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (user_id, user_name, order_id, notification_type, title, message,
              priority, scheduled_for, action_url, metadata or '{}'))
        
        notif_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return notif_id
    except Exception as e:
        print(f"Ошибка создания уведомления: {e}")
        return None

def get_unread_count(user_id):
    """Количество непрочитанных уведомлений"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM notifications 
            WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE
        """, (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"Ошибка подсчета уведомлений: {e}")
        return 0

def check_order_overdue(order):
    """Проверка просрочки заказа (старше 48 часов)"""
    if order['status'] == 'Выдан':
        return False
    from datetime import datetime, timedelta
    created_at = order['created_at']
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if datetime.now() - created_at > timedelta(hours=48):
        return True
    return False

# ------------------------------------------
# ЧАТ
# ------------------------------------------

@app.route('/chat')
@login_required
def chat_page():
    """Страница чата"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute("""
            SELECT * FROM chat_messages 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
        chat_messages = cur.fetchall()
        chat_messages = list(reversed(chat_messages))
        
        cur.close()
        conn.close()
        
        return render_template('chat.html',
                             chat_messages=chat_messages,
                             employees=get_employees(),
                             shops=Config.SHOPS)
    except Exception as e:
        print(f"Ошибка чата: {e}")
        flash('Ошибка загрузки чата', 'error')
        return render_template('chat.html',
                             chat_messages=[],
                             employees=get_employees(),
                             shops=Config.SHOPS)

# ------------------------------------------
# УВЕДОМЛЕНИЯ
# ------------------------------------------

@app.route('/notifications')
@login_required
def notifications_page():
    """Страница всех уведомлений"""
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        
        filter_type = request.args.get('type', 'all')
        search = request.args.get('search', '')
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        query = """
            SELECT n.*, 
                   o.customer as order_customer,
                   o.product as order_product,
                   o.status as order_status
            FROM notifications n
            LEFT JOIN orders o ON n.order_id = o.id
            WHERE n.user_id = %s
        """
        params = [user_id]
        
        if filter_type == 'unread':
            query += " AND n.is_read = FALSE AND n.is_archived = FALSE"
        elif filter_type == 'read':
            query += " AND n.is_read = TRUE AND n.is_archived = FALSE"
        elif filter_type == 'archived':
            query += " AND n.is_archived = TRUE"
        
        if search:
            query += " AND (n.title ILIKE %s OR n.message ILIKE %s)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
        
        query += " ORDER BY n.created_at DESC LIMIT 100"
        
        cur.execute(query, params)
        notifications = cur.fetchall()
        
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_read = FALSE AND is_archived = FALSE) as unread,
                COUNT(*) FILTER (WHERE is_archived = TRUE) as archived
            FROM notifications 
            WHERE user_id = %s
        """, (user_id,))
        stats = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return render_template('notifications.html',
                             notifications=notifications,
                             stats=stats,
                             filter_type=filter_type,
                             search=search,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка уведомлений: {e}")
        flash('Ошибка загрузки уведомлений', 'error')
        return render_template('notifications.html',
                             notifications=[],
                             stats={'total': 0, 'unread': 0, 'archived': 0},
                             shops=Config.SHOPS,
                             employees=get_employees())

@app.route('/api/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE notifications 
            SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
        """, (notif_id, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE notifications 
            SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND is_read = FALSE
        """, (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/archive/<int:notif_id>', methods=['POST'])
@login_required
def archive_notification(notif_id):
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE notifications 
            SET is_archived = TRUE
            WHERE id = %s AND user_id = %s
        """, (notif_id, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ------------------------------------------
# КАЛЕНДАРЬ
# ------------------------------------------

@app.route('/calendar')
@login_required
def calendar_page():
    """Страница календаря с заказами"""
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        is_admin = session.get('is_admin', False)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Получаем настройки уведомлений
        cur.execute("""
            SELECT * FROM notification_settings 
            WHERE user_id = %s
        """, (user_id,))
        settings = cur.fetchone()
        
        if not settings:
            cur.execute("""
                INSERT INTO notification_settings (user_id, user_name)
                VALUES (%s, %s)
                RETURNING *
            """, (user_id, user_name))
            settings = cur.fetchone()
            conn.commit()
        
        cur.close()
        conn.close()
        
        return render_template('calendar.html',
                             settings=settings,
                             shops=Config.SHOPS,
                             employees=get_employees())
    except Exception as e:
        print(f"Ошибка календаря: {e}")
        flash('Ошибка загрузки календаря', 'error')
        return render_template('calendar.html',
                             settings=None,
                             shops=Config.SHOPS,
                             employees=get_employees())

@app.route('/api/calendar/events')
@login_required
def calendar_events_api():
    """API для событий календаря"""
    try:
        user_name = session.get('user_name')
        is_admin = session.get('is_admin', False)
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
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
        cur.close()
        conn.close()
        
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
                    'start': order['created_at'].isoformat() if order['created_at'] else None,
                    'color': status_colors.get(order['status'], '#95a5a6'),
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order['id'],
                        'customer': order['customer'],
                        'product': order['product'],
                        'status': order['status'],
                        'priority': order['priority'],
                        'executor': order['executor'],
                        'shop_id': order['shop_id']
                    }
                })
            
            if order['status'] == 'Выдан' and order['completed_at']:
                events.append({
                    'id': f"completed_{order['id']}",
                    'title': f"✅ #{order['id']} {order['customer'][:15]}",
                    'start': order['completed_at'].isoformat() if order['completed_at'] else None,
                    'color': '#2ecc71',
                    'textColor': 'white',
                    'extendedProps': {
                        'order_id': order['id'],
                        'status': 'Выдан'
                    }
                })
        
        return jsonify(events)
    except Exception as e:
        print(f"Ошибка API календаря: {e}")
        return jsonify([]), 500

# ------------------------------------------
# НАСТРОЙКИ УВЕДОМЛЕНИЙ
# ------------------------------------------

@app.route('/api/notifications/settings', methods=['GET', 'POST'])
@login_required
def notification_settings_api():
    """Получение и обновление настроек уведомлений"""
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        if request.method == 'GET':
            cur.execute("""
                SELECT * FROM notification_settings 
                WHERE user_id = %s
            """, (user_id,))
            settings = cur.fetchone()
            
            if not settings:
                cur.execute("""
                    INSERT INTO notification_settings (user_id, user_name)
                    VALUES (%s, %s)
                    RETURNING *
                """, (user_id, session.get('user_name')))
                settings = cur.fetchone()
                conn.commit()
            
            cur.close()
            conn.close()
            return jsonify(dict(settings))
        
        elif request.method == 'POST':
            data = request.get_json()
            
            cur.execute("""
                UPDATE notification_settings 
                SET 
                    notify_new_orders = %s,
                    notify_status_changes = %s,
                    notify_mentions = %s,
                    notify_overdue = %s,
                    notify_chat_messages = %s,
                    notify_assignments = %s,
                    reminder_frequency = %s,
                    reminder_start_hour = %s,
                    reminder_end_hour = %s,
                    email_notifications = %s,
                    browser_notifications = %s,
                    telegram_notifications = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING *
            """, (
                data.get('notify_new_orders', True),
                data.get('notify_status_changes', True),
                data.get('notify_mentions', True),
                data.get('notify_overdue', True),
                data.get('notify_chat_messages', True),
                data.get('notify_assignments', True),
                data.get('reminder_frequency', 60),
                data.get('reminder_start_hour', 9),
                data.get('reminder_end_hour', 20),
                data.get('email_notifications', False),
                data.get('browser_notifications', True),
                data.get('telegram_notifications', False),
                user_id
            ))
            
            settings = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({'success': True, 'settings': dict(settings)})
            
    except Exception as e:
        print(f"Ошибка настроек: {e}")
        return jsonify({'error': str(e)}), 500

# ------------------------------------------
# ОНЛАЙН-СТАТУС (дополнение к чату)
# ------------------------------------------

@app.route('/api/online/update', methods=['POST'])
@login_required
def update_online_status():
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_sessions (user_id, user_name, last_seen, is_online)
            VALUES (%s, %s, CURRENT_TIMESTAMP, TRUE)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                last_seen = CURRENT_TIMESTAMP,
                is_online = TRUE,
                user_name = EXCLUDED.user_name
        """, (user_id, user_name))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/online/users')
@login_required
def get_online_users():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
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
        cur.close()
        conn.close()
        return jsonify([dict(user) for user in users])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/online/leave', methods=['POST'])
@login_required
def leave_online():
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE user_sessions 
            SET is_online = FALSE, last_seen = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
