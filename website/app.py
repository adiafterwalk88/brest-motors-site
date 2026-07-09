from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
import time
import requests

app = Flask(__name__)

ORDERS_FILE = 'orders.json'
# Пароль для входа
PASSWORD = "brest2026"

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def send_telegram(text):
    try:
        TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
        URL = f"https://api.telegram.org/bot{TOKEN}"
        requests.post(f"{URL}/sendMessage", json={
            "chat_id": "8171279171",
            "text": text,
            "parse_mode": "HTML"
        })
    except:
        pass

# ============ АВТОРИЗАЦИЯ ============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == PASSWORD:
            return redirect(url_for('home'))
        return render_template('login.html', error='Неверный пароль')
    return render_template('login.html')

# ============ ГЛАВНАЯ (ЗАКАЗЫ) ============
@app.route('/')
def home():
    orders = load_orders()
    active = [o for o in orders if o.get('status') != 'Выполнен']
    done = [o for o in orders if o.get('status') == 'Выполнен']
    return render_template('index.html', orders=orders, active=active, done=done, all_count=len(orders), active_count=len(active))

# ============ API ============
@app.route('/api/orders', methods=['GET'])
def get_orders():
    return jsonify(load_orders())

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.json
    orders = load_orders()
    
    order = {
        'id': len(orders) + 1,
        'date': time.strftime('%d.%m.%Y %H:%M'),
        'status': 'Новый',
        'customer': data.get('customer', ''),
        'phone': data.get('phone', ''),
        'address': data.get('address', ''),
        'product': data.get('product', ''),
        'price': float(data.get('price', 0)),
        'prepaid': float(data.get('prepaid', 0)),
        'priority': data.get('priority', 'normal'),
        'executor': data.get('executor', 'Не назначен'),
        'comment': data.get('comment', ''),
        'url': data.get('url', ''),
        'source': data.get('source', 'Сайт')
    }
    
    orders.append(order)
    save_orders(orders)
    
    # Уведомление в Telegram
    staff_msg = f"🖥 <b>Новый заказ с ПК №{order['id']}!</b>\n"
    staff_msg += f"👤 {order['customer']}\n"
    staff_msg += f"📱 {order['phone']}\n"
    staff_msg += f"📍 {order['address']}\n"
    staff_msg += f"📝 {order['product']}\n"
    staff_msg += f"💰 {order['price']} Br\n"
    if order['comment']: staff_msg += f"💬 {order['comment']}"
    send_telegram(staff_msg)
    
    return jsonify({'ok': True, 'order_id': order['id']})

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_status(order_id):
    data = request.json
    orders = load_orders()
    for o in orders:
        if o['id'] == order_id:
            o['status'] = data.get('status', o['status'])
            if data.get('executor'):
                o['executor'] = data['executor']
            save_orders(orders)
            return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Не найден'}), 404

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    orders = load_orders()
    orders = [o for o in orders if o['id'] != order_id]
    save_orders(orders)
    return jsonify({'ok': True})

@app.route('/api/stats')
def get_stats():
    orders = load_orders()
    total = len(orders)
    active = len([o for o in orders if o.get('status') != 'Выполнен'])
    done = len([o for o in orders if o.get('status') == 'Выполнен'])
    total_sum = sum(o.get('price', 0) for o in orders)
    debt = sum(o.get('price', 0) - o.get('prepaid', 0) for o in orders if o.get('status') != 'Выполнен')
    
    # По исполнителям
    executors = {}
    for o in orders:
        ex = o.get('executor', 'Не назначен')
        executors[ex] = executors.get(ex, 0) + o.get('price', 0)
    
    return jsonify({
        'total': total, 'active': active, 'done': done,
        'total_sum': total_sum, 'debt': debt,
        'executors': executors
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=True)
