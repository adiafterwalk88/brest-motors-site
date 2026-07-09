import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = "brest-motors-secret-key-2026"

app.jinja_env.globals.update(hasattr=hasattr)

DATABASE_URL = "postgresql://postgres:8026009Wall!@db.ophusgconubcufrobzyc.supabase.co:5432/postgres?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

class SupabaseDirectBackend:
    def table(self, table_name):
        class QueryBuilder:
            def select(self, *args): return self
            def order(self, *args, **kwargs): return self
            def execute(self):
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(f"SELECT * FROM {table_name} ORDER BY id ASC;")
                    data = cur.fetchall()
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"Ошибка БД: {e}")
                    data = []
                class Result:
                    def __init__(self, d): self.data = [dict(row) for row in d]
                return Result(data)
        return QueryBuilder()

supabase = SupabaseDirectBackend()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

EXECUTORS = ['Не назначен', 'Иван', 'Петр', 'Сергей', 'Админ']
STATUSES = ['Новый', 'В работе', 'Готов', 'Выдан']
PRIORITIES = ['Обычный', 'Высокий', 'Низкий']

@app.route('/')
@app.route('/orders')
@login_required
def dashboard():
    all_orders = supabase.table('orders').select('*').execute().data
    
    all_count = len(all_orders)
    active_count = sum(1 for o in all_orders if o.get('status') != 'Выдан')
    today_str = datetime.today().strftime('%Y-%m-%d')
    today_count = sum(1 for o in all_orders if str(o.get('created_at', '')).startswith(today_str))
    total_sum = sum(float(o.get('price') or 0) for o in all_orders)
    debt = sum(float(o.get('price') or 0) - float(o.get('prepaid') or 0) for o in all_orders if o.get('status') != 'Выдан')

    exec_stats = {}
    for o in all_orders:
        ex = o.get('executor') or 'Не назначен'
        if ex not in exec_stats: exec_stats[ex] = {'count': 0, 'sum': 0}
        exec_stats[ex]['count'] += 1
        exec_stats[ex]['sum'] += float(o.get('price') or 0)

    return render_template('dashboard.html', orders=all_orders, all_count=all_count,
        active_count=active_count, today_count=today_count, total_sum=int(total_sum),
        debt=int(max(0, debt)), exec_stats=exec_stats, current_page='orders',
        executors=EXECUTORS, statuses=STATUSES, priorities=PRIORITIES)

@app.route('/orders/create', methods=['POST'])
@login_required
def create_order():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (customer, phone, address, product, price, prepaid, priority, executor, status, comment)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            request.form.get('customer', ''),
            request.form.get('phone', ''),
            request.form.get('address', ''),
            request.form.get('product', ''),
            float(request.form.get('price', 0)),
            float(request.form.get('prepaid', 0)),
            request.form.get('priority', 'Обычный'),
            request.form.get('executor', 'Не назначен'),
            request.form.get('status', 'Новый'),
            request.form.get('comment', '')
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Ошибка сохранения: {e}")
    return redirect(url_for('dashboard'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE orders SET status=%s, executor=%s, customer=%s, phone=%s,
            product=%s, price=%s, prepaid=%s, comment=%s
            WHERE id=%s
        """, (
            request.form.get('status'),
            request.form.get('executor'),
            request.form.get('customer'),
            request.form.get('phone'),
            request.form.get('product'),
            float(request.form.get('price', 0)),
            float(request.form.get('prepaid', 0)),
            request.form.get('comment', ''),
            order_id
        ))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Ошибка обновления: {e}")
    return redirect(url_for('dashboard'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE id=%s", (order_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Ошибка удаления: {e}")
    return redirect(url_for('dashboard'))

@app.route('/clients')
@login_required
def clients():
    all_clients = supabase.table('clients').select('*').execute().data
    return render_template('clients.html', clients=all_clients or [], current_page='clients', exec_stats={})

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == '8026009Wall!':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        error = 'Неверный пароль'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
