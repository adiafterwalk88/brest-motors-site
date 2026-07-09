from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json
import os
import time
import requests
from functools import wraps

app = Flask(__name__)
app.secret_key = 'brest-motors-secret-key-2026'

ORDERS_FILE = 'orders.json'
CLIENTS_FILE = 'clients.json'
PASSWORD = "brest2026"

EXECUTORS = ['Не назначен', 'Иван', 'Петр', 'Сергей', 'Админ']
STATUSES = ['Новый', 'В работе', 'Готов', 'Выдан']
PRIORITIES = ['Низкий', 'Обычный', 'Высокий']

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
    orders = load_json(ORDERS_FILE)
    clients = load_json(CLIENTS_FILE)
    
    active = [o for o in orders if o.get('status') != 'Выдан']
    today_orders = [o for o in orders if o.get('date', '').startswith(time.strftime('%d.%m.%Y'))]
    total_sum = sum(o.get('price', 0) for o in orders)
    debt = sum(o.get('price', 0) - o.get('prepaid', 0) for o in active)
    
    # Статистика по исполнителям
    exec_stats = {}
    for o in orders:
        ex = o.get('executor', 'Не назначен')
        exec_stats[ex] = exec_stats.get(ex, {'count': 0, 'sum': 0})
        exec_stats[ex]['count'] += 1
        exec_stats[ex]['sum'] += o.get('price', 0)
    
    return render_template('dashboard.html',
        orders=orders, clients=clients, active=active,
        today_orders=today_orders, total_sum=total_sum, debt=debt,
        exec_stats=exec_stats, active_count=len(active),
        all_count=len(orders), today_count=len(today_orders),
        client_count=len(clients))

# ============ ЗАКАЗЫ ============
@app.route('/orders')
@login_required
def orders_page():
    orders = load_json(ORDERS_FILE)
    status_filter = request.args.get('status', '')
    executor_filter = request.args.get('executor', '')
    search = request.args.get('search', '').lower()
    
    filtered = orders
    if status_filter:
        filtered = [o for o in filtered if o.get('status') == status_filter]
    if executor_filter:
        filtered = [o for o in filtered if o.get('executor') == executor_filter]
    if search:
        filtered = [o for o in filtered if search in str(o).lower()]
    
    # Сортировка: новые сверху
    filtered.sort(key=lambda x: x.get('id', 0), reverse=True)
    
    return render_template('orders.html',
        orders=filtered, all_orders=orders,
        executors=EXECUTORS, statuses=STATUSES,
        current_status=status_filter, current_executor=executor_filter,
        search=search)

@app.route('/orders/add', methods=['POST'])
@login_required
def add_order():
    orders = load_json(ORDERS_FILE)
    
    order = {
        'id': len(orders) + 1,
        'date': time.strftime('%d.%m.%Y %H:%M'),
        'status': request.form.get('status', 'Новый'),
        'customer': request.form.get('customer', ''),
        'phone': request.form.get('phone', ''),
        'address': request.form.get('address', ''),
        'product': request.form.get('product', ''),
        'price': float(request.form.get('price', 0)),
        'prepaid': float(request.form.get('prepaid', 0)),
        'priority': request.form.get('priority', 'Обычный'),
        'executor': request.form.get('executor', 'Не назначен'),
        'comment': request.form.get('comment', ''),
        'source': 'Сайт'
    }
    
    orders.append(order)
    save_json(ORDERS_FILE, orders)
    
    # Сохраняем клиента
    clients = load_json(CLIENTS_FILE)
    phone = order['phone']
    if phone and not any(c.get('phone') == phone for c in clients):
        clients.append({
            'id': len(clients) + 1,
            'name': order['customer'],
            'phone': phone,
            'address': order['address'],
            'order_count': 1,
            'total_sum': order['price'],
            'created': time.strftime('%d.%m.%Y')
        })
    elif phone:
        for c in clients:
            if c.get('phone') == phone:
                c['order_count'] = c.get('order_count', 0) + 1
                c['total_sum'] = c.get('total_sum', 0) + order['price']
    save_json(CLIENTS_FILE, clients)
    
    send_telegram(f"💻 <b>Новый заказ с ПК №{order['id']}!</b>\n👤 {order['customer']}\n📱 {order['phone']}\n📝 {order['product']}\n💰 {order['price']} Br")
    
    return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    orders = load_json(ORDERS_FILE)
    for o in orders:
        if o['id'] == order_id:
            o['status'] = request.form.get('status', o['status'])
            o['executor'] = request.form.get('executor', o['executor'])
            o['customer'] = request.form.get('customer', o['customer'])
            o['phone'] = request.form.get('phone', o['phone'])
            o['product'] = request.form.get('product', o['product'])
            o['price'] = float(request.form.get('price', o['price']))
            o['prepaid'] = float(request.form.get('prepaid', o.get('prepaid', 0)))
            o['comment'] = request.form.get('comment', o.get('comment', ''))
            save_json(ORDERS_FILE, orders)
            break
    return redirect(url_for('orders_page'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    orders = load_json(ORDERS_FILE)
    orders = [o for o in orders if o['id'] != order_id]
    save_json(ORDERS_FILE, orders)
    return redirect(url_for('orders_page'))

# ============ КЛИЕНТЫ ============
@app.route('/clients')
@login_required
def clients_page():
    clients = load_json(CLIENTS_FILE)
    orders = load_json(ORDERS_FILE)
    
    # Обновляем статистику клиентов
    for c in clients:
        client_orders = [o for o in orders if o.get('phone') == c.get('phone')]
        c['order_count'] = len(client_orders)
        c['total_sum'] = sum(o.get('price', 0) for o in client_orders)
    
    return render_template('clients.html', clients=clients)

# ============ API ============
@app.route('/api/orders', methods=['GET'])
def api_orders():
    return jsonify(load_json(ORDERS_FILE))

@app.route('/api/stats')
def api_stats():
    orders = load_json(ORDERS_FILE)
    active = [o for o in orders if o.get('status') != 'Выдан']
    return jsonify({
        'total': len(orders),
        'active': len(active),
        'today': len([o for o in orders if o.get('date', '').startswith(time.strftime('%d.%m.%Y'))]),
        'sum': sum(o.get('price', 0) for o in orders),
        'debt': sum(o.get('price', 0) - o.get('prepaid', 0) for o in active)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
