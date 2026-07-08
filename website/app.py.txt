from flask import Flask, render_template, request, jsonify
import json
import os
import time

app = Flask(__name__)

# Файл с заказами
ORDERS_FILE = 'orders.json'

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_orders(orders):
    with open(ORDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/catalog')
def catalog():
    return render_template('catalog.html')

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
        'name': data.get('name', ''),
        'phone': data.get('phone', ''),
        'address': data.get('address', ''),
        'product': data.get('product', ''),
        'price': data.get('price', 0),
        'comment': data.get('comment', ''),
        'source': 'Сайт'
    }
    
    orders.append(order)
    save_orders(orders)
    
    # Отправка в Telegram (если настроен бот)
    try:
        import requests
        TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
        URL = f"https://api.telegram.org/bot{TOKEN}"
        staff_msg = f"🌐 <b>Новый заказ с сайта №{order['id']}!</b>\n"
        staff_msg += f"👤 {order['name']}\n"
        staff_msg += f"📱 {order['phone']}\n"
        staff_msg += f"📍 {order['address']}\n"
        staff_msg += f"📝 {order['product']}\n"
        staff_msg += f"💰 {order['price']} Br\n"
        if order['comment']: staff_msg += f"💬 {order['comment']}"
        requests.post(f"{URL}/sendMessage", json={
            "chat_id": "8171279171",
            "text": staff_msg,
            "parse_mode": "HTML"
        })
    except:
        pass
    
    return jsonify({'ok': True, 'order_id': order['id']})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=True)