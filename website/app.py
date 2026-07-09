from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps
import time
import requests
import os  # <-- ИСПРАВЛЕНО: Добавлен импорт модуля для работы с окружением Render
from supabase import create_client

app = Flask(__name__)
app.secret_key = 'brest-motors-secret-key-2026'

SUPABASE_URL = "https://oi1gbpcpcjfrZ6ZocysTuw.supabase.co"
SUPABASE_KEY = "sb_publishable_Oi1gbpCpzhfrZ6ZocysTuw__bbAJRzA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

PASSWORD = "brest2026"
EXECUTORS = ['Не назначен', 'Иван', 'Петр', 'Сергей', 'Админ']
STATUSES = ['Новый', 'В работе', 'Готов', 'Выдан']

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def send_telegram(text):
    try:
        TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": "8171279171", "text": text, "parse_mode": "HTML"
        })
    except: pass

# ============ АВТОРИЗАЦИЯ ============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Неверный пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============ ДАШБОРД ============
@app.route('/')
@login_required
def dashboard():
    all_orders = supabase.table('orders').select('*').order('id', desc=True).execute().data
    clients = supabase.table('clients').select('*').execute().data
    
    active = [o for o in all_orders if o.get('status') != 'Выдан']
    today_orders = [o for o in all_orders if o.get('created_at', '').startswith(time.strftime('%Y-%m-%d'))]
    total_sum = sum(o.get('price', 0) for o in all_orders)
    debt = sum(o.get('price', 0) - o.get('prepaid', 0) for o in active)
    
    exec_stats = {}
    for o in all_orders:
        ex = o.get('executor', 'Не назначен')
        exec_stats[ex] = exec_stats.get(ex, {'count': 0, 'sum': 0})
        exec_stats[ex]['count'] += 1
        exec_stats[ex]['sum'] += o.get('price', 0)
    
    return render_template('dashboard.html',
        orders=all_orders, clients=clients or [], active=active,
        today_orders=today_orders, total_sum=total_sum, debt=debt,
        exec_stats=exec_stats, active_count=len(active),
        all_count=len(all_orders), today_count=len(today_orders),
        client_count=len(clients or []))

# ============ ЗАКАЗЫ ============
@app.route('/orders')
@login_required
def orders_page():
    all_orders = supabase.table('orders').select('*').order('id', desc=True).execute().data
    status_filter = request.args.get('status', '')
    executor_filter = request.args.get('executor', '')
    search = request.args.get('search', '').lower()
    
    filtered = all_orders
    if status_filter:
        filtered = [o for o in filtered if o.get('status') == status_filter]
    if executor_filter:
        filtered = [o for o in filtered if o.get('executor') == executor_filter]
    if search:
        filtered = [o for o in filtered if search in str(o).lower()]
    
    return render_template('orders.html',
        orders=filtered, all_orders=all_orders,
        executors=EXECUTORS, statuses=STATUSES,
        current_status=status_filter, current_executor=executor_filter,
        search=search)

@app.route('/orders/add', methods=['POST'])
@login_required
def add_order():
    order = {
        'customer': request.form.get('customer', ''),
        'phone': request.form.get('phone', ''),
        'address': request.form.get('address', ''),
        'product': request.form.get('product', ''),
        'price': float(request.form.get('price', 0)),
        'prepaid': float(request.form.get('prepaid', 0)),
        'priority': request.form.get('priority', 'Обычный'),
        'executor': request.form.get('executor', 'Не назначен'),
        'status': request.form.get('status', 'Новый'),
        'comment': request.form.get('comment', ''),
        'source': 'Сайт'
    }
    supabase.table('orders').insert(order).execute()
    
    # Обновляем клиента
    phone = order['phone']
    if phone:
        existing = supabase.table('clients').select('*').eq('phone', phone).execute()
        if existing.data:
            c = existing.data[0]
            supabase.table('clients').update({
                'orders_count': c.get('orders_count', 0) + 1,
                'total_sum': c.get('total_sum', 0) + order['price']
            }).eq('phone', phone).execute()
        else:
            supabase.table('clients').insert({
                'name': order['customer'],
                'phone': phone,
                'address': order['address'],
                'orders_count': 1,
                'total_sum': order['price']
            }).execute()
    
    send_telegram(f"💻 Новый заказ с ПК!\n👤 {order['customer']}\n📱 {order['phone']}\n📝 {order['product']}\n💰 {order['price']} Br")
    return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    data = {
        'status': request.form.get('status'),
        'executor': request.form.get('executor'),
        'customer': request.form.get('customer'),
        'phone': request.form.get('phone'),
        'product': request.form.get('product'),
        'price': float(request.form.get('price', 0)),
        'prepaid': float(request.form.get('prepaid', 0)),
        'comment': request.form.get('comment'),
    }
    supabase.table('orders').update(data).eq('id', order_id).execute()
    return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    supabase.table('orders').delete().eq('id', order_id).execute()
    return redirect(url_for('orders_page'))

# ============ КЛИЕНТЫ ============
@app.route('/clients')
@login_required
def clients_page():
    clients = supabase.table('clients').select('*').order('total_sum', desc=True).execute().data
    return render_template('clients.html', clients=clients or [])

# ============ API ============
@app.route('/api/orders')
def api_orders():
    res = supabase.table('orders').select('*').eq('status', 'Новый').execute()
    return jsonify(res.data)

@app.route('/api/stats')
def api_stats():
    orders = supabase.table('orders').select('*').execute().data
    active = [o for o in orders if o.get('status') != 'Выдан']
    return jsonify({
        'total': len(orders),
        'active': len(active),
        'sum': sum(o.get('price', 0) for o in orders),
        'debt': sum(o.get('price', 0) - o.get('prepaid', 0) for o in active)
    })

# ============ ЗАПУСК ПРИЛОЖЕНИЯ ============
if __name__ == '__main__':
    # ИСПРАВЛЕНО: Чистый запуск на динамическом порту Render (по умолчанию 10000)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
