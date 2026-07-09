import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', 'BrestMotors2026_Secret_Key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'BrestMotorsPassword')

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL', 'postgresql://postgres.ophusgconubcufrobzyc:8026009Wall!@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?pgbouncer=true')
    conn = psycopg2.connect(db_url)
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def safe_float(value, default=0.0):
    if not value:
        return default
    try:
        return float(value.strip().replace(',', '.'))
    except ValueError:
        return default

# ==========================================
# АВТОРИЗАЦИЯ
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный пароль доступа', 'error')
    return render_template('dashboard.html', current_page='login', orders=[], exec_stats={})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# ДАШБОРД
# ==========================================
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;")
    orders = cur.fetchall()
    
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
        'total_orders': total_orders,
        'active_orders': active_orders,
        'today_orders': today_orders,
        'total_revenue': total_revenue,
        'pending_payment': pending_payment
    }
    
    return render_template('dashboard.html', current_page='dashboard', orders=orders, metrics=metrics, exec_stats=exec_stats)

# ==========================================
# ВСЕ ЗАКАЗЫ
# ==========================================
@app.route('/orders')
@login_required
def list_orders():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('dashboard.html', current_page='orders', orders=orders, exec_stats={})

# ==========================================
# СОЗДАНИЕ ЗАКАЗА
# ==========================================
@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
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

        try:
            conn = get_db_connection()
            conn.autocommit = True  
            cur = conn.cursor()
            query = """
                INSERT INTO orders (customer, phone, address, product, price, prepaid, priority, executor, status, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(query, (customer, phone, address, product, price, prepaid, priority, executor, status, comment))
            cur.close()
            conn.close()
            flash('Заказ успешно создан!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"Ошибка БД: {e}")
            flash(f'Ошибка при создании заказа: {e}', 'error')
            return redirect(url_for('create_order'))

    return render_template('dashboard.html', current_page='create_order', orders=[], exec_stats={})

# ==========================================
# КЛИЕНТЫ (БАЗА)
# ==========================================
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
        print(f"Ошибка в /clients: {e}")
        flash(f'Ошибка загрузки клиентов: {e}', 'error')
        return redirect(url_for('dashboard'))

# ==========================================
# РЕДАКТИРОВАНИЕ ЗАКАЗА
# ==========================================
@app.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
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
        
        try:
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
            flash('Заказ успешно обновлён!', 'success')
            return redirect(url_for('list_orders'))
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка при обновлении: {e}', 'error')
    
    cur.execute("SELECT * FROM orders WHERE id = %s;", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    
    if not order:
        flash('Заказ не найден', 'error')
        return redirect(url_for('list_orders'))
    
    return render_template('dashboard.html', 
                         current_page='edit_order', 
                         order=order, 
                         orders=[], 
                         exec_stats={})

# ==========================================
# API ДЛЯ ПРИЛОЖЕНИЯ
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
        return jsonify({"error": str(e)}), 500

# ==========================================
# ОБРАБОТКА ОШИБОК
# ==========================================
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Page not found", "url": request.url}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
