import os
import logging
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

from flask import (
    Flask, render_template, request, jsonify, flash, redirect,
    url_for, session
)
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')

class Config:
    DATABASE_URL = os.environ.get('DATABASE_URL')
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
            logger.info("Пул соединений PostgreSQL создан.")
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

def normalize_order(order):
    """Нормализует ключи словаря заказа для гарантированного отображения в шаблоне"""
    if not order:
        return order
    
    # Преобразуем RealDictRow в обычный dict
    d = dict(order)
    
    # Клиент
    d['customer_name'] = d.get('customer_name') or d.get('client_name') or d.get('client') or d.get('fio') or ''
    # Телефон
    d['customer_phone'] = d.get('customer_phone') or d.get('phone') or d.get('client_phone') or ''
    # Устройство
    d['device_model'] = d.get('device_model') or d.get('device') or d.get('model') or ''
    d['device_type'] = d.get('device_type') or d.get('type') or ''
    # Мастер
    d['executor'] = d.get('executor') or d.get('master') or d.get('mechanic') or ''
    # Сумма
    d['estimated_cost'] = d.get('estimated_cost') or d.get('price') or d.get('cost') or d.get('sum') or 0
    
    return d

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# РОУТЫ
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
                    return redirect(url_for('orders_page'))
                else:
                    flash('Неверное имя пользователя или пароль', 'error')
        except Exception as e:
            flash(f'Ошибка входа: {e}', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return redirect(url_for('orders_page'))

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
            raw_orders = cur.fetchall()
            
            # Применяем нормализацию к каждому заказу
            orders = [normalize_order(o) for o in raw_orders]

            cur.execute("SELECT COUNT(*) FROM orders WHERE is_archived = TRUE;")
            res_archived = cur.fetchone()
            archived_count = res_archived['count'] if res_archived else 0
        
        return render_template(
            'orders.html',
            orders=orders,
            search=search,
            show_archived=show_archived,
            archived_count=archived_count,
            shops=Config.SHOPS,
            total_count=len(orders),
            active_page='orders'
        )
    except Exception as e:
        logger.exception("Ошибка загрузки заказов")
        flash(f'Ошибка загрузки заказов: {e}', 'error')
        return render_template('orders.html', orders=[], shops=Config.SHOPS, active_page='orders', total_count=0)

@app.route('/set-shop/<shop_id>')
@login_required
def set_shop(shop_id):
    if shop_id in Config.SHOPS or shop_id == 'all':
        session['shop_id'] = shop_id
    return redirect(request.referrer or url_for('orders_page'))

# --- Роуты бокового меню (убирают 404) ---

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
                flash('Заказ успешно создан!', 'success')
                return redirect(url_for('orders_page'))
        except Exception as e:
            flash(f'Ошибка при создании заказа: {e}', 'error')
            
    return render_template('order_form.html', employees=Config.EMPLOYEES, shops=Config.SHOPS)

init_db_pool()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
