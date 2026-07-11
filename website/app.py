import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
import psycopg2
from psycopg2.extras import DictCursor
import secrets

# ==========================================
# ЗАГРУЗКА ПЕРЕМЕННЫХ ИЗ .env
# ==========================================
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

# Проверка обязательных переменных
if not Config.ADMIN_PASSWORD:
    raise ValueError("❌ ADMIN_PASSWORD не найден! Установите в .env файле")
if not Config.DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден! Установите в .env файле")

# ==========================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ==========================================
app = Flask(__name__)  # <-- ГЛАВНОЕ: переменная называется 'app'
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_db_connection():
    """Подключение к базе данных"""
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        raise

def safe_float(value, default=0.0):
    """Безопасное преобразование в число"""
    if not value or not str(value).strip():
        return default
    try:
        return float(str(value).strip().replace(',', '.'))
    except ValueError:
        return default

def login_required(f):
    """Декоратор для проверки авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# МАРШРУТЫ
# ==========================================

# --- Авторизация ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == Config.ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            flash('✅ Успешный вход!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('❌ Неверный пароль!', 'error')
    return render_template('dashboard.html', current_page='login', orders=[], exec_stats={})

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

# --- Дашборд ---
@app.route('/')
@login_required
def dashboard():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Получаем последние заказы
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;")
        orders = cur.fetchall()
        
        # Статистика
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Завершен') FROM orders;")
        total_orders, active_orders = cur.fetchone()
        
        cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
        today_orders = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(SUM(price), 0), COALESCE(SUM(price - prepaid) FILTER (WHERE status != 'Завершен'), 0) FROM orders;")
        total_revenue, pending_payment = cur.fetchone()
        
        cur.execute("""
            SELECT executor, COUNT(*) as count, COALESCE(SUM(price), 0) as total_sum 
            FROM orders 
            WHERE status != 'Завершен'
            GROUP BY executor;
        """)
        exec_stats = cur.fetchall()
        
        cur.close()
        conn.close()
        
        metrics = {
            'total_orders': total_orders or 0,
            'active_orders': active_orders or 0,
            'today_orders': today_orders or 0,
            'total_revenue': total_revenue or 0,
            'pending_payment': pending_payment or 0
        }
        
        return render_template('dashboard.html', 
                             current_page='dashboard', 
                             orders=orders, 
                             metrics=metrics, 
                             exec_stats=exec_stats)
    except Exception as e:
        print(f"Ошибка дашборда: {e}")
        flash('Ошибка загрузки данных', 'error')
        return render_template('dashboard.html', current_page='dashboard', orders=[], exec_stats={})

# --- Список заказов ---
@app.route('/orders')
@login_required
def list_orders():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
        orders = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('dashboard.html', current_page='orders', orders=orders, exec_stats={})
    except Exception as e:
        print(f"Ошибка списка заказов: {e}")
        flash('Ошибка загрузки заказов', 'error')
        return redirect(url_for('dashboard'))

# --- Создание заказа ---
@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
        try:
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
            url = request.form.get('url')
            
            conn = get_db_connection()
            cur = conn.cursor()
            query = """
                INSERT INTO orders (customer, phone, address, product, price, prepaid, 
                                   priority, executor, status, comment, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """
            cur.execute(query, (customer, phone, address, product, price, prepaid, 
                               priority, executor, status, comment, url))
            order_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            
            flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            print(f"Ошибка создания заказа: {e}")
            flash(f'❌ Ошибка при создании: {e}', 'error')
            return redirect(url_for('create_order'))
    
    return render_template('dashboard.html', current_page='create_order', orders=[], exec_stats={})

# --- Клиенты ---
@app.route('/clients')
@login_required
def list_clients():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT customer, phone, COUNT(*) as total_orders, SUM(price) as total_spent
            FROM orders
            GROUP BY customer, phone
            ORDER BY total_spent DESC;
        """)
        clients = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('dashboard.html', current_page='clients', clients=clients, orders=[], exec_stats={})
    except Exception as e:
        print(f"Ошибка загрузки клиентов: {e}")
        flash('Ошибка загрузки клиентов', 'error')
        return redirect(url_for('dashboard'))

# --- Редактирование заказа ---
@app.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        try:
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
            url = request.form.get('url')
            
            query = """
                UPDATE orders 
                SET customer = %s, phone = %s, address = %s, product = %s, 
                    price = %s, prepaid = %s, priority = %s, executor = %s, 
                    status = %s, comment = %s, url = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            """
            cur.execute(query, (customer, phone, address, product, price, 
                              prepaid, priority, executor, status, comment, url, order_id))
            conn.commit()
            flash('✅ Заказ успешно обновлён!', 'success')
            return redirect(url_for('list_orders'))
        except Exception as e:
            conn.rollback()
            print(f"Ошибка обновления: {e}")
            flash(f'❌ Ошибка при обновлении: {e}', 'error')
    
    cur.execute("SELECT * FROM orders WHERE id = %s;", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    
    if not order:
        flash('❌ Заказ не найден', 'error')
        return redirect(url_for('list_orders'))
    
    return render_template('dashboard.html', 
                         current_page='edit_order', 
                         order=order, 
                         orders=[], 
                         exec_stats={})

# ==========================================
# API МАРШРУТЫ
# ==========================================
@app.route('/api/orders')
def api_orders():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM orders WHERE status = 'Новый' ORDER BY id ASC;")
        data = cur.fetchall()
        cur.close()
        conn.close()
        
        result = []
        for row in data:
            r = dict(row)
            for k, v in r.items():
                if hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
            result.append(r)
        return jsonify(result)
    except Exception as e:
        print(f"API ошибка: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/orders/<int:order_id>', methods=['PUT', 'PATCH'])
def api_update_order(order_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        allowed_fields = ['customer', 'phone', 'address', 'product', 'price', 
                         'prepaid', 'priority', 'executor', 'status', 'comment', 'url']
        
        updates = []
        values = []
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])
        
        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(order_id)
        
        query = f"UPDATE orders SET {', '.join(updates)} WHERE id = %s;"
        cur.execute(query, values)
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order updated"})
    except Exception as e:
        print(f"API ошибка обновления: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# ОБРАБОТКА ОШИБОК
# ==========================================
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Page not found", "url": request.url}), 404

@app.errorhandler(500)
def internal_error(e):
    print(f"Внутренняя ошибка: {e}")
    return jsonify({"error": "Internal server error"}), 500

# ==========================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG)
