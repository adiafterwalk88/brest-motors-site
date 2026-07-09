import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import psycopg2
from psycopg2.extras import DictCursor

app = Flask(__name__)

# Секретный ключ для сессий и пароль администратора
app.secret_key = os.environ.get('SECRET_KEY', 'BrestMotors2026_Secret_Key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'BrestMotorsPassword')

# Функция подключения к вашей базе данных PostgreSQL (Supabase)
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL', 'your_supabase_postgresql_connection_string_here')
    conn = psycopg2.connect(db_url)
    return conn

# Декоратор для защиты страниц от неавторизованных пользователей
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- МАРШРУТЫ АВТОРИЗАЦИИ ---

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

# --- ГЛАВНАЯ СТРАНИЦА / ДАШБОРД ---

@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # 1. Получаем последние 10 заказов садовой техники
    cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;")
    orders = cur.fetchall()
    
    # 2. Считаем базовые метрики магазина
    cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status != 'Завершен') FROM orders;")
    total_orders, active_orders = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE;")
    today_orders = cur.fetchone()[0]
    
    # 3. Финансовая аналитика (Выручка и Долг по предзаказам)
    cur.execute("SELECT COALESCE(SUM(price), 0), COALESCE(SUM(price - prepaid) FILTER (WHERE status != 'Завершен'), 0) FROM orders;")
    total_revenue, pending_payment = cur.fetchone()
    
    # 4. Нагрузка на сотрудников (сборка, предпродажная подготовка техники)
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
    
    return render_template(
        'dashboard.html', 
        current_page='dashboard', 
        orders=orders, 
        metrics=metrics, 
        exec_stats=exec_stats
    )

# --- МАРШРУТЫ ДЛЯ ЗАКАЗОВ ---

@app.route('/orders')
@login_required
def list_orders():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM orders ORDER BY DESC;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('dashboard.html', current_page='orders', orders=orders, exec_stats={})

@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
        # Данные БЕЗ источника заказа
        customer = request.form.get('customer')
        phone = request.form.get('phone')
        address = request.form.get('address')
        product = request.form.get('product')
        
        price = request.form.get('price')
        price = float(price) if price else 0.0
        
        prepaid = request.form.get('prepaid')
        prepaid = float(prepaid) if prepaid else 0.0

        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment')

        try:
            conn = get_db_connection()
            conn.autocommit = True  
            cur = conn.cursor()
            
            # Ровно 10 полей садовой техники
            query = """
                INSERT INTO orders (customer, phone, address, product, price, prepaid, priority, executor, status, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(query, (customer, phone, address, product, price, prepaid, priority, executor, status, comment))
            cur.close()
            conn.close()
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"Ошибка БД: {e}")
            return redirect(url_for('dashboard'))

    return render_template('dashboard.html', current_page='create_order', orders=[], exec_stats={})

# --- ПРОСМОТР КЛИЕНТОВ ---

@app.route('/clients')
@login_required
def list_clients():
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

# Для gunicorn этот блок не важен, но оставим его для локальных тестов дома
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
