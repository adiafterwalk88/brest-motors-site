import os
import secrets
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client
from datetime import datetime
from functools import wraps
import bcrypt

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 60 * 60

SUPABASE_URL = "https://ophusgconubcufrobzyc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9waHVzZ2NvbnViY3Vmcm9ienljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM1ODc5MjQsImV4cCI6MjA5OTE2MzkyNH0.a1DBm4PkDt1NHHyIDfF_xFqZd7qEhSGwUfdZbnvXKXs"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Подключение к Supabase установлено!")

STORES = [
    {'id': 1, 'name': 'Магазин Карьерная', 'executors': ['Павел Иванович', 'Александр']},
    {'id': 2, 'name': 'Магазин Московская', 'executors': ['Паша', 'Дмитрий']}
]

def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def render_page(content, **kwargs):
    return render_template_string(BASE_TEMPLATE, content=content, **kwargs)

def get_store_name(store_id):
    for s in STORES:
        if s['id'] == store_id:
            return s['name']
    return 'Неизвестный магазин'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CRM Заказы</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f0f2f5; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 20px; }
        .header { background: #2c3e50; color: #fff; padding: 15px 0; }
        .header-content { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .header h1 { font-size: 20px; font-weight: 400; }
        .header nav { display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
        .header nav a { color: rgba(255,255,255,0.8); text-decoration: none; padding: 5px 10px; border-radius: 4px; font-size: 14px; }
        .header nav a:hover { background: rgba(255,255,255,0.1); color: #fff; }
        .user-info { color: rgba(255,255,255,0.7); font-size: 13px; }
        .btn { display: inline-block; padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; text-decoration: none; }
        .btn-primary { background: #3498db; color: #fff; }
        .btn-primary:hover { background: #2980b9; }
        .btn-success { background: #2ecc71; color: #fff; }
        .btn-success:hover { background: #27ae60; }
        .btn-danger { background: #e74c3c; color: #fff; }
        .btn-danger:hover { background: #c0392b; }
        .btn-secondary { background: #95a5a6; color: #fff; }
        .btn-secondary:hover { background: #7f8c8d; }
        .btn-outline { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,0.3); }
        .btn-outline:hover { background: rgba(255,255,255,0.1); }
        .btn-sm { padding: 4px 10px; font-size: 12px; }
        .btn-full { width: 100%; }
        .auth-container { display: flex; justify-content: center; align-items: center; min-height: 80vh; }
        .auth-card { background: #fff; padding: 35px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); width: 100%; max-width: 380px; }
        .auth-card h2 { text-align: center; margin-bottom: 25px; color: #2c3e50; font-weight: 400; }
        .auth-hint { text-align: center; margin-top: 15px; font-size: 13px; color: #7f8c8d; }
        .auth-hint a { color: #3498db; text-decoration: none; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 4px; font-weight: 500; font-size: 13px; color: #555; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; transition: border 0.2s; font-family: inherit; }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: #3498db; outline: none; }
        .flash-messages { margin-bottom: 15px; }
        .flash { padding: 10px 15px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; }
        .flash-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .flash-warning { background: #fff3cd; color: #856404; border: 1px solid #ffc107; }
        .flash-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 20px; background: #fff; padding: 15px 20px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
        .search-box { flex: 1; min-width: 150px; }
        .search-box input { width: 100%; padding: 6px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
        .search-box input:focus { border-color: #3498db; outline: none; }
        .filter-group select { padding: 6px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; background: #fff; cursor: pointer; }
        .orders-table { width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
        .orders-table th { background: #f8f9fa; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; color: #555; border-bottom: 2px solid #eee; }
        .orders-table td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
        .orders-table tr:hover { background: #f8f9fa; }
        .orders-table .status { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
        .status-Новый { background: #3498db; color: #fff; }
        .status-В-работе { background: #f39c12; color: #fff; }
        .status-Готов { background: #2ecc71; color: #fff; }
        .status-Отменен { background: #e74c3c; color: #fff; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); justify-content: center; align-items: center; }
        .modal-content { background: #fff; padding: 25px 30px; border-radius: 12px; max-width: 600px; width: 95%; max-height: 90vh; overflow-y: auto; position: relative; }
        .modal-close { position: absolute; right: 18px; top: 12px; font-size: 24px; cursor: pointer; color: #999; }
        .modal-close:hover { color: #333; }
        .modal h2 { margin-bottom: 20px; font-weight: 400; color: #2c3e50; font-size: 20px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .form-actions { display: flex; gap: 10px; margin-top: 15px; }
        .form-actions .btn { flex: 1; text-align: center; }
        .empty-state { text-align: center; padding: 40px 20px; color: #999; }
        .empty-state h3 { color: #555; margin-bottom: 5px; font-weight: 400; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
        .badge-executor { background: #e8f8f0; color: #27ae60; }
        .badge-priority { background: #fef9e7; color: #d4ac0d; }
        .badge-source { background: #f0f0f0; color: #666; }
        @media (max-width: 768px) {
            .form-row { grid-template-columns: 1fr; }
            .header-content { flex-direction: column; gap: 10px; text-align: center; }
            .header nav { justify-content: center; }
            .orders-table { font-size: 12px; }
            .orders-table th, .orders-table td { padding: 6px 8px; }
            .modal-content { padding: 15px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="container">
            <div class="header-content">
                <h1>📋 CRM Заказы</h1>
                {% if session.user_id %}
                <nav>
                    <a href="/orders">Заказы</a>
                    <span class="user-info">{{ session.username }} | {{ session.store_name }}</span>
                    <a href="/logout" class="btn btn-outline btn-sm">Выйти</a>
                </nav>
                {% endif %}
            </div>
        </div>
    </header>
    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        {{ content|safe }}
    </main>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<div class="auth-container">
    <div class="auth-card">
        <h2>Вход в систему</h2>
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" placeholder="example@mail.com" required />
            </div>
            <div class="form-group">
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" placeholder="••••••••" required />
            </div>
            <button type="submit" class="btn btn-primary btn-full">Войти</button>
            <p class="auth-hint">Нет аккаунта? <a href="/register">Зарегистрироваться</a></p>
        </form>
    </div>
</div>
'''

REGISTER_TEMPLATE = '''
<div class="auth-container">
    <div class="auth-card">
        <h2>Регистрация</h2>
        <form method="POST" action="/register">
            <div class="form-group">
                <label for="username">Имя пользователя</label>
                <input type="text" id="username" name="username" placeholder="ivanov" required />
            </div>
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" placeholder="example@mail.com" required />
            </div>
            <div class="form-group">
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" placeholder="••••••••" required />
            </div>
            <div class="form-group">
                <label for="password_confirm">Подтверждение пароля</label>
                <input type="password" id="password_confirm" name="password_confirm" placeholder="••••••••" required />
            </div>
            <div class="form-group">
                <label for="store">Магазин</label>
                <select id="store" name="store" required>
                    <option value="1">Магазин Карьерная</option>
                    <option value="2">Магазин Московская</option>
                </select>
            </div>
            <button type="submit" class="btn btn-success btn-full">Зарегистрироваться</button>
            <p class="auth-hint">Уже есть аккаунт? <a href="/login">Войти</a></p>
        </form>
    </div>
</div>
'''

ORDERS_TEMPLATE = '''
<div style="margin: 15px 0;">
    <button class="btn btn-primary" onclick="document.getElementById('orderModal').style.display='flex'; document.getElementById('modalTitle').textContent='Новый заказ'; document.getElementById('orderId').value=''; document.getElementById('orderForm').reset();">+ Новый заказ</button>
</div>

<div class="toolbar">
    <div class="search-box">
        <input type="text" id="searchInput" placeholder="Поиск по клиенту или телефону..." oninput="loadOrders()" />
    </div>
    <div class="filter-group">
        <select id="statusFilter" onchange="loadOrders()">
            <option value="all">Все статусы</option>
            <option value="Новый">Новый</option>
            <option value="В работе">В работе</option>
            <option value="Готов">Готов</option>
            <option value="Отменен">Отменен</option>
        </select>
    </div>
    <div style="font-size:13px;color:#999;">
        Всего: <span id="totalCount">0</span> заказов
    </div>
</div>

<div id="ordersContainer">
    <div class="empty-state">Загрузка...</div>
</div>

<!-- Модалка создания/редактирования -->
<div id="orderModal" class="modal">
    <div class="modal-content">
        <span class="modal-close" onclick="document.getElementById('orderModal').style.display='none'">&times;</span>
        <h2 id="modalTitle">Новый заказ</h2>
        <form id="orderForm" onsubmit="saveOrder(event)">
            <input type="hidden" id="orderId" />
            <div class="form-row">
                <div class="form-group">
                    <label for="customer">Клиент</label>
                    <input type="text" id="customer" placeholder="Имя клиента" required />
                </div>
                <div class="form-group">
                    <label for="phone">Телефон</label>
                    <input type="text" id="phone" placeholder="+375 XX XXX-XX-XX" required />
                </div>
            </div>
            <div class="form-group">
                <label for="address">Адрес</label>
                <input type="text" id="address" placeholder="Адрес доставки" />
            </div>
            <div class="form-group">
                <label for="product">Товар/услуга</label>
                <input type="text" id="product" placeholder="Наименование товара или услуги" />
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="price">Цена (₽)</label>
                    <input type="number" id="price" placeholder="0" step="0.01" min="0" />
                </div>
                <div class="form-group">
                    <label for="prepaid">Предоплата (₽)</label>
                    <input type="number" id="prepaid" placeholder="0" step="0.01" min="0" />
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="executor">Исполнитель</label>
                    <select id="executor">
                        <option value="Не назначен">Не назначен</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="priority">Приоритет</label>
                    <select id="priority">
                        <option value="Низкий">Низкий</option>
                        <option value="Обычный" selected>Обычный</option>
                        <option value="Высокий">Высокий</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label for="status">Статус</label>
                    <select id="status">
                        <option value="Новый">Новый</option>
                        <option value="В работе">В работе</option>
                        <option value="Готов">Готов</option>
                        <option value="Отменен">Отменен</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="source">Источник</label>
                    <select id="source">
                        <option value="Сайт">Сайт</option>
                        <option value="Телефон">Телефон</option>
                        <option value="Мессенджер">Мессенджер</option>
                        <option value="Лично">Лично</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label for="comment">Комментарий</label>
                <textarea id="comment" rows="2" placeholder="Дополнительная информация..."></textarea>
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-success">Сохранить</button>
                <button type="button" class="btn btn-secondary" onclick="document.getElementById('orderModal').style.display='none'">Отмена</button>
            </div>
        </form>
    </div>
</div>

<!-- Модалка удаления -->
<div id="deleteModal" class="modal">
    <div class="modal-content" style="max-width:400px;">
        <h2>Подтверждение</h2>
        <p>Удалить заказ клиента <strong id="deleteCustomerName"></strong>?</p>
        <div class="form-actions">
            <button class="btn btn-danger" onclick="confirmDelete()">Удалить</button>
            <button class="btn btn-secondary" onclick="document.getElementById('deleteModal').style.display='none'">Отмена</button>
        </div>
    </div>
</div>

<script>
// ===== КНОПКА "НОВЫЙ ЗАКАЗ" =====
document.getElementById('newOrderBtn').addEventListener('click', function() {
    document.getElementById('orderModal').style.display = 'flex';
    document.getElementById('modalTitle').textContent = 'Новый заказ';
    document.getElementById('orderId').value = '';
    document.getElementById('orderForm').reset();
    document.getElementById('customer').value = '';
    document.getElementById('phone').value = '';
    document.getElementById('address').value = '';
    document.getElementById('product').value = '';
    document.getElementById('price').value = '';
    document.getElementById('prepaid').value = '';
    document.getElementById('status').value = 'Новый';
    document.getElementById('priority').value = 'Обычный';
    document.getElementById('source').value = 'Сайт';
    document.getElementById('comment').value = '';
    // Исполнители для Магазина Московская (по умолчанию)
    var select = document.getElementById('executor');
    select.innerHTML = '<option value="Не назначен">Не назначен</option><option value="Павел Иванович">Павел Иванович</option><option value="Александр">Александр</option><option value="Паша">Паша</option><option value="Дмитрий">Дмитрий</option>';
});

function closeModal() {
    document.getElementById('orderModal').style.display = 'none';
}

function loadOrders() {
    fetch('/api/orders')
        .then(function(response) { return response.json(); })
        .then(function(orders) {
            var container = document.getElementById('ordersContainer');
            if (orders.length === 0) {
                container.innerHTML = '<div class="empty-state"><h3>Нет заказов</h3><p>Создайте первый заказ</p></div>';
                return;
            }
            var html = '<div style="overflow-x:auto;"><table class="orders-table"><thead><tr>';
            html += '<th>ID</th><th>Клиент</th><th>Телефон</th><th>Товар</th>';
            html += '<th>Цена</th><th>Предоплата</th><th>Исполнитель</th><th>Статус</th><th>Действия</th>';
            html += '</tr></thead><tbody>';
            for (var i = 0; i < orders.length; i++) {
                var o = orders[i];
                var statusClass = o.status === 'Новый' ? 'status-Новый' : 
                                 o.status === 'В работе' ? 'status-В-работе' : 
                                 o.status === 'Готов' ? 'status-Готов' : 'status-Отменен';
                html += '<tr>';
                html += '<td>#' + o.id + '</td>';
                html += '<td><strong>' + (o.customer || '-') + '</strong></td>';
                html += '<td>' + (o.phone || '-') + '</td>';
                html += '<td>' + (o.product || '-') + '</td>';
                html += '<td>' + (o.price ? Number(o.price).toFixed(2) + ' ₽' : '-') + '</td>';
                html += '<td>' + (o.prepaid ? Number(o.prepaid).toFixed(2) + ' ₽' : '-') + '</td>';
                html += '<td><span class="badge badge-executor">' + (o.executor || 'Не назначен') + '</span></td>';
                html += '<td><span class="status ' + statusClass + '">' + o.status + '</span></td>';
                html += '<td>';
                html += '<button class="btn btn-primary btn-sm" onclick="openEditModal(' + o.id + ')">✎</button> ';
                html += '<button class="btn btn-danger btn-sm" onclick="openDeleteModal(' + o.id + ',\'' + (o.customer || 'без имени') + '\')">✕</button>';
                html += '</td>';
                html += '</tr>';
            }
            html += '</tbody></table></div>';
            container.innerHTML = html;
            document.getElementById('totalCount').textContent = orders.length;
        })
        .catch(function(error) {
            console.error('Ошибка:', error);
        });
}

function openEditModal(id) {
    fetch('/api/orders')
        .then(function(response) { return response.json(); })
        .then(function(orders) {
            var order = null;
            for (var i = 0; i < orders.length; i++) {
                if (orders[i].id == id) {
                    order = orders[i];
                    break;
                }
            }
            if (!order) { alert('Заказ не найден'); return; }
            document.getElementById('orderId').value = order.id;
            document.getElementById('modalTitle').textContent = 'Редактирование заказа';
            document.getElementById('customer').value = order.customer || '';
            document.getElementById('phone').value = order.phone || '';
            document.getElementById('address').value = order.address || '';
            document.getElementById('product').value = order.product || '';
            document.getElementById('price').value = order.price || '';
            document.getElementById('prepaid').value = order.prepaid || '';
            document.getElementById('status').value = order.status || 'Новый';
            document.getElementById('priority').value = order.priority || 'Обычный';
            document.getElementById('source').value = order.source || 'Сайт';
            document.getElementById('comment').value = order.comment || '';
            var select = document.getElementById('executor');
            select.innerHTML = '<option value="Не назначен">Не назначен</option><option value="Павел Иванович">Павел Иванович</option><option value="Александр">Александр</option><option value="Паша">Паша</option><option value="Дмитрий">Дмитрий</option>';
            document.getElementById('executor').value = order.executor || 'Не назначен';
            document.getElementById('orderModal').style.display = 'flex';
        })
        .catch(function(error) {
            console.error('Ошибка:', error);
        });
}

function saveOrder(e) {
    e.preventDefault();
    var id = document.getElementById('orderId').value;
    var data = {
        customer: document.getElementById('customer').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        address: document.getElementById('address').value.trim(),
        product: document.getElementById('product').value.trim(),
        price: parseFloat(document.getElementById('price').value) || 0,
        prepaid: parseFloat(document.getElementById('prepaid').value) || 0,
        executor: document.getElementById('executor').value,
        priority: document.getElementById('priority').value,
        status: document.getElementById('status').value,
        source: document.getElementById('source').value,
        comment: document.getElementById('comment').value.trim()
    };
    var url = id ? '/api/orders/' + id : '/api/orders';
    var method = id ? 'PUT' : 'POST';
    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(function(response) {
        if (response.ok) {
            document.getElementById('orderModal').style.display = 'none';
            loadOrders();
        } else {
            alert('Ошибка сохранения');
        }
    })
    .catch(function(error) {
        alert('Ошибка: ' + error.message);
    });
}

function openDeleteModal(id, name) {
    deleteTargetId = id;
    document.getElementById('deleteCustomerName').textContent = name;
    document.getElementById('deleteModal').style.display = 'flex';
}

var deleteTargetId = null;

function confirmDelete() {
    if (!deleteTargetId) return;
    fetch('/api/orders/' + deleteTargetId, { method: 'DELETE' })
        .then(function(response) {
            if (response.ok) {
                document.getElementById('deleteModal').style.display = 'none';
                deleteTargetId = null;
                loadOrders();
            } else {
                alert('Ошибка удаления');
            }
        })
        .catch(function(error) {
            alert('Ошибка: ' + error.message);
        });
}

window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadOrders();
});

console.log('✅ Все функции загружены!');
</script>
'''

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect('/orders')
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = supabase.table('app_users').select('*').eq('email', email).execute()
            if user.data and check_password(password, user.data[0]['password_hash']):
                session.permanent = True
                session['user_id'] = user.data[0]['id']
                session['username'] = user.data[0]['username']
                session['store_id'] = user.data[0]['store_id']
                session['store_name'] = get_store_name(user.data[0]['store_id'])
                flash(f'Добро пожаловать, {user.data[0]["username"]}!', 'success')
                return redirect('/orders')
            else:
                flash('Неверный email или пароль', 'danger')
        except Exception as e:
            flash(f'Ошибка входа: {str(e)}', 'danger')
    return render_page(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        store_id = int(request.form.get('store'))
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_page(REGISTER_TEMPLATE)
        
        try:
            existing_email = supabase.table('app_users').select('*').eq('email', email).execute()
            if existing_email.data:
                flash('Email уже используется', 'danger')
                return render_page(REGISTER_TEMPLATE)
            
            existing_user = supabase.table('app_users').select('*').eq('username', username).execute()
            if existing_user.data:
                flash('Имя пользователя уже занято', 'danger')
                return render_page(REGISTER_TEMPLATE)
            
            password_hash = hash_password(password)
            
            supabase.table('app_users').insert({
                'username': username,
                'email': email,
                'password_hash': password_hash,
                'store_id': store_id
            }).execute()
            
            flash('Регистрация успешна! Войдите в систему.', 'success')
            return redirect('/login')
            
        except Exception as e:
            flash(f'Ошибка регистрации: {str(e)}', 'danger')
    
    return render_page(REGISTER_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect('/login')

@app.route('/orders')
@login_required
def orders():
    return render_page(ORDERS_TEMPLATE)

@app.route('/api/orders')
@login_required
def api_orders():
    try:
        orders = supabase.table('orders').select('*').order('created_at', desc=True).execute()
        return jsonify([{
            'id': o['id'],
            'customer': o.get('customer', ''),
            'phone': o.get('phone', ''),
            'address': o.get('address', ''),
            'product': o.get('product', ''),
            'price': o.get('price', 0),
            'prepaid': o.get('prepaid', 0),
            'executor': o.get('executor', 'Не назначен'),
            'priority': o.get('priority', 'Обычный'),
            'status': o.get('status', 'Новый'),
            'source': o.get('source', 'Сайт'),
            'comment': o.get('comment', ''),
            'created_at': o['created_at']
        } for o in orders.data])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders', methods=['POST'])
@login_required
def api_create_order():
    try:
        data = request.json
        result = supabase.table('orders').insert({
            'customer': data.get('customer', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),
            'product': data.get('product', ''),
            'price': data.get('price', 0),
            'prepaid': data.get('prepaid', 0),
            'executor': data.get('executor', 'Не назначен'),
            'priority': data.get('priority', 'Обычный'),
            'status': data.get('status', 'Новый'),
            'source': data.get('source', 'Сайт'),
            'comment': data.get('comment', '')
        }).execute()
        
        phone = data.get('phone', '')
        if phone:
            existing_client = supabase.table('clients').select('*').eq('phone', phone).execute()
            if existing_client.data:
                supabase.table('clients').update({
                    'orders_count': existing_client.data[0]['orders_count'] + 1,
                    'total_sum': existing_client.data[0]['total_sum'] + data.get('price', 0)
                }).eq('phone', phone).execute()
            else:
                supabase.table('clients').insert({
                    'name': data.get('customer', ''),
                    'phone': phone,
                    'address': data.get('address', ''),
                    'orders_count': 1,
                    'total_sum': data.get('price', 0)
                }).execute()
        
        return jsonify({'id': result.data[0]['id'], 'message': 'Заказ создан'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def api_update_order(order_id):
    try:
        data = request.json
        order = supabase.table('orders').select('*').eq('id', order_id).execute()
        if not order.data:
            return jsonify({'error': 'Заказ не найден'}), 404
        supabase.table('orders').update({
            'customer': data.get('customer', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),
            'product': data.get('product', ''),
            'price': data.get('price', 0),
            'prepaid': data.get('prepaid', 0),
            'executor': data.get('executor', 'Не назначен'),
            'priority': data.get('priority', 'Обычный'),
            'status': data.get('status', 'Новый'),
            'source': data.get('source', 'Сайт'),
            'comment': data.get('comment', '')
        }).eq('id', order_id).execute()
        return jsonify({'message': 'Заказ обновлен'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
@login_required
def api_delete_order(order_id):
    try:
        order = supabase.table('orders').select('*').eq('id', order_id).execute()
        if not order.data:
            return jsonify({'error': 'Заказ не найден'}), 404
        supabase.table('orders').delete().eq('id', order_id).execute()
        return jsonify({'message': 'Заказ удален'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
