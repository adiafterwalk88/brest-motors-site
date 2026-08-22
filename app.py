import os
import secrets
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime, Text, Boolean
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ===== Базовый класс для SQLAlchemy =====
class Base(DeclarativeBase):
    pass

# ===== Инициализация приложения =====
app = Flask(__name__)

# ===== Генерация SECRET_KEY =====
if os.environ.get('FLASK_DEBUG') == 'False' or os.environ.get('RENDER'):
    app.secret_key = os.environ.get('SECRET_KEY')
    if not app.secret_key:
        app.secret_key = secrets.token_hex(32)
        print("⚠️ ВНИМАНИЕ: Используется временный SECRET_KEY!")
else:
    app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ===== Конфигурация базы данных =====
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

# ===== Инициализация БД =====
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# ============================================
# ===== ВСЕ ШАБЛОНЫ В ОДНОМ МЕСТЕ =====
# ============================================

BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Brest Motors CRM</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 20px; }
        .header { background: linear-gradient(135deg, #2c3e50, #1a252f); color: #fff; padding: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .header-content { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .header h1 { font-size: 24px; }
        .header nav { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
        .header nav a { color: rgba(255,255,255,0.8); text-decoration: none; padding: 5px 10px; border-radius: 4px; }
        .header nav a:hover { background: rgba(255,255,255,0.1); color: #fff; }
        .header nav a.active { background: rgba(52,152,219,0.3); color: #fff; }
        .user-info { color: rgba(255,255,255,0.7); font-size: 14px; }
        .btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.3s; text-decoration: none; }
        .btn-primary { background: #3498db; color: #fff; }
        .btn-primary:hover { background: #2980b9; transform: translateY(-2px); }
        .btn-success { background: #2ecc71; color: #fff; }
        .btn-success:hover { background: #27ae60; transform: translateY(-2px); }
        .btn-danger { background: #e74c3c; color: #fff; }
        .btn-danger:hover { background: #c0392b; transform: translateY(-2px); }
        .btn-secondary { background: #95a5a6; color: #fff; }
        .btn-secondary:hover { background: #7f8c8d; }
        .btn-outline { background: transparent; color: #fff; border: 2px solid rgba(255,255,255,0.3); }
        .btn-outline:hover { background: rgba(255,255,255,0.1); border-color: #fff; }
        .btn-sm { padding: 5px 12px; font-size: 12px; }
        .btn-full { width: 100%; justify-content: center; }
        .auth-container { display: flex; justify-content: center; align-items: center; min-height: 80vh; }
        .auth-card { background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); width: 100%; max-width: 420px; }
        .auth-card h2 { text-align: center; margin-bottom: 30px; color: #2c3e50; }
        .auth-hint { text-align: center; margin-top: 15px; font-size: 14px; color: #7f8c8d; }
        .auth-hint a { color: #3498db; text-decoration: none; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 6px; font-weight: 600; font-size: 14px; color: #555; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 12px 16px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; transition: border 0.3s; font-family: inherit; }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: #3498db; outline: none; }
        .flash-messages { margin-bottom: 20px; }
        .flash { padding: 12px 20px; border-radius: 8px; margin-bottom: 10px; font-weight: 500; }
        .flash-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-danger { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .flash-warning { background: #fff3cd; color: #856404; border: 1px solid #ffc107; }
        .flash-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .toolbar { display: flex; flex-wrap: wrap; gap: 15px; align-items: center; margin-bottom: 25px; background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .search-box { flex: 1; min-width: 200px; position: relative; }
        .search-box input { width: 100%; padding: 10px 14px 10px 40px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; }
        .search-box input:focus { border-color: #3498db; outline: none; }
        .filter-group select { padding: 10px 16px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 14px; background: #fff; cursor: pointer; }
        .orders-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .order-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); transition: all 0.3s; border-left: 4px solid #3498db; }
        .order-card:hover { transform: translateY(-4px); box-shadow: 0 8px 25px rgba(0,0,0,0.1); }
        .order-card .order-number { font-weight: 700; font-size: 18px; color: #2c3e50; }
        .order-card .order-client { color: #7f8c8d; font-size: 14px; margin: 4px 0 10px; }
        .order-card .order-amount { font-size: 22px; font-weight: 700; color: #2c3e50; }
        .order-card .order-amount small { font-size: 14px; font-weight: 400; color: #7f8c8d; }
        .order-card .order-status { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; text-transform: uppercase; margin-top: 8px; }
        .status-новый { background: #3498db; color: #fff; }
        .status-в-работе { background: #f39c12; color: #fff; }
        .status-готово { background: #2ecc71; color: #fff; }
        .status-отменен { background: #e74c3c; color: #fff; }
        .order-card .order-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
        .order-card .order-date { font-size: 12px; color: #999; }
        .order-card .order-actions { display: flex; gap: 8px; }
        .order-card .order-actions button { background: none; border: none; cursor: pointer; padding: 6px 8px; border-radius: 6px; font-size: 14px; }
        .order-card .order-actions .edit-btn:hover { background: #ebf5fb; color: #3498db; }
        .order-card .order-actions .delete-btn:hover { background: #fdedec; color: #e74c3c; }
        .employees-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .employee-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #2ecc71; }
        .employee-card h3 { color: #2c3e50; margin-bottom: 8px; }
        .employee-card p { color: #666; font-size: 14px; margin: 4px 0; }
        .employee-card .employee-actions { display: flex; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); backdrop-filter: blur(4px); justify-content: center; align-items: center; }
        .modal-content { background: #fff; padding: 30px 35px; border-radius: 16px; max-width: 560px; width: 95%; max-height: 90vh; overflow-y: auto; position: relative; }
        .modal-small { max-width: 420px; }
        .modal-close { position: absolute; right: 20px; top: 15px; font-size: 28px; cursor: pointer; color: #999; }
        .modal-close:hover { color: #333; }
        .form-actions { display: flex; gap: 12px; margin-top: 10px; }
        .form-actions .btn { flex: 1; justify-content: center; }
        .pagination { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; }
        .pagination button { padding: 8px 14px; border: 2px solid #e0e0e0; border-radius: 8px; background: #fff; cursor: pointer; transition: all 0.3s; font-weight: 600; }
        .pagination button:hover { border-color: #3498db; color: #3498db; }
        .pagination button.active { background: #3498db; color: #fff; border-color: #3498db; }
        .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
        .empty-state { text-align: center; padding: 60px 20px; color: #999; grid-column: 1 / -1; }
        .empty-state i { font-size: 60px; margin-bottom: 20px; color: #ddd; }
        .empty-state h3 { color: #555; margin-bottom: 10px; }
        .loading { text-align: center; padding: 40px; color: #999; grid-column: 1 / -1; }
        .card { background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        .section { padding: 20px 0; }
        @media (max-width: 768px) {
            .header-content { flex-direction: column; gap: 10px; text-align: center; }
            .header nav { justify-content: center; }
            .toolbar { flex-direction: column; }
            .orders-list, .employees-list { grid-template-columns: 1fr; }
            .modal-content { padding: 20px; }
            .form-actions { flex-direction: column; }
            .auth-card { padding: 25px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" />
</head>
<body>
    <header class="header">
        <div class="container">
            <div class="header-content">
                <h1><i class="fas fa-car"></i> Brest Motors CRM</h1>
                {% if session.user_id %}
                <nav>
                    <a href="{{ url_for('orders') }}" class="{% if request.endpoint == 'orders' %}active{% endif %}">
                        <i class="fas fa-box"></i> Заказы
                    </a>
                    <a href="{{ url_for('employee') }}" class="{% if request.endpoint == 'employee' %}active{% endif %}">
                        <i class="fas fa-users"></i> Сотрудники
                    </a>
                    {% if session.is_admin %}
                    <a href="{{ url_for('admin_panel') }}" class="{% if request.endpoint == 'admin_panel' %}active{% endif %}">
                        <i class="fas fa-cog"></i> Админка
                    </a>
                    {% endif %}
                    <span class="user-info"><i class="fas fa-user"></i> {{ session.username }}</span>
                    <a href="{{ url_for('logout') }}" class="btn btn-outline btn-sm">
                        <i class="fas fa-sign-out-alt"></i> Выйти
                    </a>
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
    <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/js/all.min.js"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<div class="auth-container">
    <div class="auth-card">
        <h2><i class="fas fa-lock"></i> Вход в систему</h2>
        <form method="POST">
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" placeholder="example@mail.com" required />
            </div>
            <div class="form-group">
                <label for="password">Пароль</label>
                <input type="password" id="password" name="password" placeholder="••••••••" required />
            </div>
            <button type="submit" class="btn btn-primary btn-full"><i class="fas fa-sign-in-alt"></i> Войти</button>
            <p class="auth-hint">Нет аккаунта? <a href="{{ url_for('register') }}">Зарегистрироваться</a></p>
        </form>
    </div>
</div>
'''

REGISTER_TEMPLATE = '''
<div class="auth-container">
    <div class="auth-card">
        <h2><i class="fas fa-user-plus"></i> Регистрация</h2>
        <form method="POST">
            <div class="form-group">
                <label for="username">Имя пользователя</label>
                <input type="text" id="username" name="username" placeholder="ivanov" required />
            </div>
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" placeholder="example@mail.com" required />
            </div>
            <div class="form-group">
                <label for="password">Пароль (минимум 6 символов)</label>
                <input type="password" id="password" name="password" placeholder="••••••••" required />
            </div>
            <div class="form-group">
                <label for="password_confirm">Подтверждение пароля</label>
                <input type="password" id="password_confirm" name="password_confirm" placeholder="••••••••" required />
            </div>
            <button type="submit" class="btn btn-success btn-full"><i class="fas fa-user-plus"></i> Зарегистрироваться</button>
            <p class="auth-hint">Уже есть аккаунт? <a href="{{ url_for('login') }}">Войти</a></p>
        </form>
    </div>
</div>
'''

ORDERS_TEMPLATE = '''
<section class="section">
    <div class="toolbar">
        <button id="createOrderBtn" class="btn btn-primary">
            <i class="fas fa-plus"></i> Создать заказ
        </button>
        <div class="search-box">
            <i class="fas fa-search"></i>
            <input type="text" id="searchInput" placeholder="Поиск по номеру или клиенту..." />
        </div>
        <div class="filter-group">
            <select id="statusFilter">
                <option value="all">Все статусы</option>
                <option value="новый">Новый</option>
                <option value="в работе">В работе</option>
                <option value="готово">Готово</option>
                <option value="отменен">Отменен</option>
            </select>
        </div>
    </div>
    <div id="ordersList" class="orders-list">
        <div class="loading"><i class="fas fa-spinner fa-spin"></i> Загрузка...</div>
    </div>
    <div id="pagination" class="pagination"></div>
</section>

<div id="orderModal" class="modal">
    <div class="modal-content">
        <span class="modal-close">&times;</span>
        <h2 id="modalTitle"><i class="fas fa-edit"></i> Создание заказа</h2>
        <form id="orderForm">
            <input type="hidden" id="orderId" />
            <div class="form-group">
                <label for="orderNumber">Номер заказа</label>
                <input type="text" id="orderNumber" placeholder="ORD-2024-001" required />
            </div>
            <div class="form-group">
                <label for="clientName">Клиент</label>
                <input type="text" id="clientName" placeholder="Иван Иванов" required />
            </div>
            <div class="form-group">
                <label for="orderAmount">Сумма (₽)</label>
                <input type="number" id="orderAmount" placeholder="1000" min="0" step="0.01" required />
            </div>
            <div class="form-group">
                <label for="orderStatus">Статус</label>
                <select id="orderStatus">
                    <option value="новый">Новый</option>
                    <option value="в работе">В работе</option>
                    <option value="готово">Готово</option>
                    <option value="отменен">Отменен</option>
                </select>
            </div>
            <div class="form-group">
                <label for="orderDescription">Описание</label>
                <textarea id="orderDescription" rows="3" placeholder="Детали заказа..."></textarea>
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-success"><i class="fas fa-save"></i> Сохранить</button>
                <button type="button" class="btn btn-secondary" id="cancelModalBtn"><i class="fas fa-times"></i> Отмена</button>
            </div>
        </form>
    </div>
</div>

<div id="deleteModal" class="modal">
    <div class="modal-content modal-small">
        <span class="modal-close">&times;</span>
        <h2><i class="fas fa-exclamation-triangle" style="color:#e74c3c;"></i> Подтверждение</h2>
        <p>Вы уверены, что хотите удалить заказ <strong id="deleteOrderNumber"></strong>?</p>
        <div class="form-actions">
            <button id="confirmDeleteBtn" class="btn btn-danger"><i class="fas fa-trash"></i> Удалить</button>
            <button id="cancelDeleteBtn" class="btn btn-secondary"><i class="fas fa-times"></i> Отмена</button>
        </div>
    </div>
</div>

<script>
let currentPage = 1;
const pageSize = 9;
let totalOrders = 0;
let deleteTargetId = null;

async function loadOrders() {
    const search = document.getElementById('searchInput').value.trim();
    const status = document.getElementById('statusFilter').value;
    try {
        const response = await fetch('/api/orders');
        let orders = await response.json();
        if (search) {
            orders = orders.filter(o => 
                o.order_number.toLowerCase().includes(search.toLowerCase()) ||
                o.client_name.toLowerCase().includes(search.toLowerCase())
            );
        }
        if (status !== 'all') {
            orders = orders.filter(o => o.status === status);
        }
        totalOrders = orders.length;
        const start = (currentPage - 1) * pageSize;
        const end = start + pageSize;
        const pageItems = orders.slice(start, end);
        renderOrders(pageItems);
        renderPagination();
    } catch (error) {
        console.error('Ошибка загрузки:', error);
    }
}

function renderOrders(orders) {
    const list = document.getElementById('ordersList');
    if (orders.length === 0) {
        list.innerHTML = `<div class="empty-state"><i class="fas fa-inbox"></i><h3>Нет заказов</h3><p>Создайте первый заказ</p></div>`;
        return;
    }
    list.innerHTML = orders.map(order => `
        <div class="order-card">
            <div class="order-number">${order.order_number}</div>
            <div class="order-client"><i class="fas fa-user"></i> ${order.client_name}</div>
            <div class="order-amount">${Number(order.amount).toLocaleString()} <small>₽</small></div>
            <span class="order-status status-${order.status.replace(/ /g, '-')}">${order.status}</span>
            ${order.description ? `<p style="margin-top:8px;font-size:13px;color:#666;">${order.description}</p>` : ''}
            <div class="order-meta">
                <span class="order-date"><i class="far fa-calendar-alt"></i> ${new Date(order.created_at).toLocaleDateString()}</span>
                <div class="order-actions">
                    <button class="edit-btn" data-id="${order.id}"><i class="fas fa-edit"></i></button>
                    <button class="delete-btn" data-id="${order.id}" data-number="${order.order_number}"><i class="fas fa-trash"></i></button>
                </div>
            </div>
        </div>
    `).join('');
    document.querySelectorAll('.edit-btn').forEach(btn => btn.addEventListener('click', () => openEditModal(btn.dataset.id)));
    document.querySelectorAll('.delete-btn').forEach(btn => btn.addEventListener('click', () => openDeleteModal(btn.dataset.id, btn.dataset.number)));
}

function renderPagination() {
    const totalPages = Math.ceil(totalOrders / pageSize);
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    if (totalPages <= 1) return;
    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadOrders(); } });
    pagination.appendChild(prevBtn);
    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        if (i === currentPage) btn.classList.add('active');
        btn.addEventListener('click', () => { currentPage = i; loadOrders(); });
        pagination.appendChild(btn);
    }
    const nextBtn = document.createElement('button');
    nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; loadOrders(); } });
    pagination.appendChild(nextBtn);
}

document.getElementById('createOrderBtn').addEventListener('click', () => {
    document.getElementById('orderId').value = '';
    document.getElementById('orderNumber').value = '';
    document.getElementById('clientName').value = '';
    document.getElementById('orderAmount').value = '';
    document.getElementById('orderStatus').value = 'новый';
    document.getElementById('orderDescription').value = '';
    document.getElementById('modalTitle').innerHTML = '<i class="fas fa-plus-circle"></i> Создание заказа';
    document.getElementById('orderModal').style.display = 'flex';
});

async function openEditModal(id) {
    try {
        const response = await fetch('/api/orders');
        const orders = await response.json();
        const order = orders.find(o => o.id == id);
        if (!order) { alert('Заказ не найден'); return; }
        document.getElementById('orderId').value = order.id;
        document.getElementById('orderNumber').value = order.order_number;
        document.getElementById('clientName').value = order.client_name;
        document.getElementById('orderAmount').value = order.amount;
        document.getElementById('orderStatus').value = order.status;
        document.getElementById('orderDescription').value = order.description || '';
        document.getElementById('modalTitle').innerHTML = '<i class="fas fa-edit"></i> Редактирование заказа';
        document.getElementById('orderModal').style.display = 'flex';
    } catch (error) { console.error('Ошибка:', error); }
}

document.getElementById('orderForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('orderId').value;
    const data = {
        order_number: document.getElementById('orderNumber').value.trim(),
        client_name: document.getElementById('clientName').value.trim(),
        amount: parseFloat(document.getElementById('orderAmount').value),
        status: document.getElementById('orderStatus').value,
        description: document.getElementById('orderDescription').value.trim()
    };
    const url = id ? `/api/orders/${id}` : '/api/orders';
    const method = id ? 'PUT' : 'POST';
    try {
        const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (response.ok) {
            document.getElementById('orderModal').style.display = 'none';
            document.getElementById('orderForm').reset();
            loadOrders();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.error || 'Неизвестная ошибка'));
        }
    } catch (error) { alert('Ошибка: ' + error.message); }
});

function openDeleteModal(id, number) {
    deleteTargetId = id;
    document.getElementById('deleteOrderNumber').textContent = number;
    document.getElementById('deleteModal').style.display = 'flex';
}

document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
    if (!deleteTargetId) return;
    try {
        const response = await fetch(`/api/orders/${deleteTargetId}`, { method: 'DELETE' });
        if (response.ok) {
            document.getElementById('deleteModal').style.display = 'none';
            deleteTargetId = null;
            loadOrders();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.error || 'Неизвестная ошибка'));
        }
    } catch (error) { alert('Ошибка: ' + error.message); }
});

document.getElementById('cancelDeleteBtn').addEventListener('click', () => {
    document.getElementById('deleteModal').style.display = 'none';
    deleteTargetId = null;
});

document.querySelectorAll('.modal-close').forEach(close => {
    close.addEventListener('click', () => {
        document.getElementById('orderModal').style.display = 'none';
        document.getElementById('deleteModal').style.display = 'none';
    });
});

document.getElementById('cancelModalBtn').addEventListener('click', () => {
    document.getElementById('orderModal').style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === document.getElementById('orderModal')) document.getElementById('orderModal').style.display = 'none';
    if (e.target === document.getElementById('deleteModal')) document.getElementById('deleteModal').style.display = 'none';
});

let searchTimeout;
document.getElementById('searchInput').addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => { currentPage = 1; loadOrders(); }, 400);
});

document.getElementById('statusFilter').addEventListener('change', () => {
    currentPage = 1;
    loadOrders();
});

loadOrders();
</script>
'''

EMPLOYEE_TEMPLATE = '''
<section class="section">
    <div class="toolbar">
        <button id="addEmployeeBtn" class="btn btn-success">
            <i class="fas fa-user-plus"></i> Добавить сотрудника
        </button>
        <div class="search-box">
            <i class="fas fa-search"></i>
            <input type="text" id="searchEmployee" placeholder="Поиск сотрудников..." />
        </div>
    </div>
    <div id="employeesList" class="employees-list">
        <div class="loading"><i class="fas fa-spinner fa-spin"></i> Загрузка...</div>
    </div>
</section>

<div id="employeeModal" class="modal">
    <div class="modal-content">
        <span class="modal-close">&times;</span>
        <h2 id="employeeModalTitle"><i class="fas fa-user-plus"></i> Добавить сотрудника</h2>
        <form id="employeeForm">
            <input type="hidden" id="employeeId" />
            <div class="form-group">
                <label for="fullName">ФИО</label>
                <input type="text" id="fullName" placeholder="Иванов Иван Иванович" required />
            </div>
            <div class="form-group">
                <label for="position">Должность</label>
                <input type="text" id="position" placeholder="Менеджер" required />
            </div>
            <div class="form-group">
                <label for="phone">Телефон</label>
                <input type="tel" id="phone" placeholder="+375 (29) 123-45-67" />
            </div>
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" placeholder="ivan@example.com" />
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-success"><i class="fas fa-save"></i> Сохранить</button>
                <button type="button" class="btn btn-secondary" id="cancelEmployeeModal"><i class="fas fa-times"></i> Отмена</button>
            </div>
        </form>
    </div>
</div>

<div id="deleteEmployeeModal" class="modal">
    <div class="modal-content modal-small">
        <span class="modal-close">&times;</span>
        <h2><i class="fas fa-exclamation-triangle" style="color:#e74c3c;"></i> Подтверждение</h2>
        <p>Вы уверены, что хотите удалить сотрудника <strong id="deleteEmployeeName"></strong>?</p>
        <div class="form-actions">
            <button id="confirmDeleteEmployeeBtn" class="btn btn-danger"><i class="fas fa-trash"></i> Удалить</button>
            <button id="cancelDeleteEmployeeBtn" class="btn btn-secondary"><i class="fas fa-times"></i> Отмена</button>
        </div>
    </div>
</div>

<script>
let deleteEmployeeId = null;

async function loadEmployees() {
    try {
        const response = await fetch('/api/employees');
        const employees = await response.json();
        const list = document.getElementById('employeesList');
        const search = document.getElementById('searchEmployee').value.toLowerCase();
        let filtered = employees;
        if (search) {
            filtered = employees.filter(e => 
                e.full_name.toLowerCase().includes(search) ||
                e.position.toLowerCase().includes(search)
            );
        }
        if (filtered.length === 0) {
            list.innerHTML = `<div class="empty-state"><i class="fas fa-users"></i><h3>Нет сотрудников</h3><p>Добавьте первого сотрудника</p></div>`;
            return;
        }
        list.innerHTML = filtered.map(emp => `
            <div class="employee-card">
                <h3><i class="fas fa-user-circle"></i> ${emp.full_name}</h3>
                <p><i class="fas fa-briefcase"></i> <strong>Должность:</strong> ${emp.position}</p>
                ${emp.phone ? `<p><i class="fas fa-phone"></i> <strong>Телефон:</strong> ${emp.phone}</p>` : ''}
                ${emp.email ? `<p><i class="fas fa-envelope"></i> <strong>Email:</strong> ${emp.email}</p>` : ''}
                <div class="employee-actions">
                    <button class="btn btn-primary btn-sm edit-employee" data-id="${emp.id}"><i class="fas fa-edit"></i></button>
                    <button class="btn btn-danger btn-sm delete-employee" data-id="${emp.id}" data-name="${emp.full_name}"><i class="fas fa-trash"></i></button>
                </div>
            </div>
        `).join('');
        document.querySelectorAll('.edit-employee').forEach(btn => btn.addEventListener('click', () => openEditEmployee(btn.dataset.id)));
        document.querySelectorAll('.delete-employee').forEach(btn => btn.addEventListener('click', () => openDeleteEmployee(btn.dataset.id, btn.dataset.name)));
    } catch (error) { console.error('Ошибка:', error); }
}

document.getElementById('addEmployeeBtn').addEventListener('click', () => {
    document.getElementById('employeeId').value = '';
    document.getElementById('fullName').value = '';
    document.getElementById('position').value = '';
    document.getElementById('phone').value = '';
    document.getElementById('email').value = '';
    document.getElementById('employeeModalTitle').innerHTML = '<i class="fas fa-user-plus"></i> Добавить сотрудника';
    document.getElementById('employeeModal').style.display = 'flex';
});

async function openEditEmployee(id) {
    try {
        const response = await fetch('/api/employees');
        const employees = await response.json();
        const emp = employees.find(e => e.id == id);
        if (!emp) { alert('Сотрудник не найден'); return; }
        document.getElementById('employeeId').value = emp.id;
        document.getElementById('fullName').value = emp.full_name;
        document.getElementById('position').value = emp.position;
        document.getElementById('phone').value = emp.phone || '';
        document.getElementById('email').value = emp.email || '';
        document.getElementById('employeeModalTitle').innerHTML = '<i class="fas fa-edit"></i> Редактировать сотрудника';
        document.getElementById('employeeModal').style.display = 'flex';
    } catch (error) { console.error('Ошибка:', error); }
}

document.getElementById('employeeForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('employeeId').value;
    const data = {
        full_name: document.getElementById('fullName').value.trim(),
        position: document.getElementById('position').value.trim(),
        phone: document.getElementById('phone').value.trim(),
        email: document.getElementById('email').value.trim()
    };
    const url = id ? `/api/employees/${id}` : '/api/employees';
    const method = id ? 'PUT' : 'POST';
    try {
        const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (response.ok) {
            document.getElementById('employeeModal').style.display = 'none';
            loadEmployees();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.error || 'Неизвестная ошибка'));
        }
    } catch (error) { alert('Ошибка: ' + error.message); }
});

function openDeleteEmployee(id, name) {
    deleteEmployeeId = id;
    document.getElementById('deleteEmployeeName').textContent = name;
    document.getElementById('deleteEmployeeModal').style.display = 'flex';
}

document.getElementById('confirmDeleteEmployeeBtn').addEventListener('click', async () => {
    if (!deleteEmployeeId) return;
    try {
        const response = await fetch(`/api/employees/${deleteEmployeeId}`, { method: 'DELETE' });
        if (response.ok) {
            document.getElementById('deleteEmployeeModal').style.display = 'none';
            deleteEmployeeId = null;
            loadEmployees();
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.error || 'Неизвестная ошибка'));
        }
    } catch (error) { alert('Ошибка: ' + error.message); }
});

document.getElementById('cancelDeleteEmployeeBtn').addEventListener('click', () => {
    document.getElementById('deleteEmployeeModal').style.display = 'none';
    deleteEmployeeId = null;
});

document.querySelectorAll('.modal-close').forEach(close => {
    close.addEventListener('click', () => {
        document.getElementById('employeeModal').style.display = 'none';
        document.getElementById('deleteEmployeeModal').style.display = 'none';
    });
});

document.getElementById('cancelEmployeeModal').addEventListener('click', () => {
    document.getElementById('employeeModal').style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === document.getElementById('employeeModal')) document.getElementById('employeeModal').style.display = 'none';
    if (e.target === document.getElementById('deleteEmployeeModal')) document.getElementById('deleteEmployeeModal').style.display = 'none';
});

let searchTimeout2;
document.getElementById('searchEmployee').addEventListener('input', () => {
    clearTimeout(searchTimeout2);
    searchTimeout2 = setTimeout(loadEmployees, 300);
});

loadEmployees();
</script>
'''

ADMIN_TEMPLATE = '''
<section class="section">
    <h2><i class="fas fa-cog"></i> Административная панель</h2>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-top:20px;">
        <div class="card"><h3><i class="fas fa-users"></i> Пользователи</h3><p style="font-size:32px;font-weight:700;color:#3498db;">{{ users|length }}</p></div>
        <div class="card"><h3><i class="fas fa-box"></i> Заказы</h3><p style="font-size:32px;font-weight:700;color:#2ecc71;">{{ orders|length }}</p></div>
        <div class="card"><h3><i class="fas fa-user-tie"></i> Сотрудники</h3><p style="font-size:32px;font-weight:700;color:#f39c12;">{{ employees|length }}</p></div>
    </div>
</section>
'''

ERROR_404 = '''
<div style="text-align:center;padding:100px 20px;">
    <i class="fas fa-search" style="font-size:80px;color:#e74c3c;"></i>
    <h1 style="font-size:48px;margin:20px 0;">404</h1>
    <h2>Страница не найдена</h2>
    <a href="{{ url_for('orders') }}" class="btn btn-primary"><i class="fas fa-home"></i> На главную</a>
</div>
'''

ERROR_500 = '''
<div style="text-align:center;padding:100px 20px;">
    <i class="fas fa-exclamation-triangle" style="font-size:80px;color:#f39c12;"></i>
    <h1 style="font-size:48px;margin:20px 0;">500</h1>
    <h2>Внутренняя ошибка сервера</h2>
    <a href="{{ url_for('orders') }}" class="btn btn-primary"><i class="fas fa-home"></i> На главную</a>
</div>
'''

# ============================================
# ===== МОДЕЛИ =====
# ============================================

class User(db.Model):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Order(db.Model):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default='новый')
    description: Mapped[str] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship('User', backref='orders', lazy=True)

class Employee(db.Model):
    __tablename__ = 'employees'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(120), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, db.ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='employees', lazy=True)

# ============================================
# ===== ДЕКОРАТОРЫ =====
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Доступ запрещен', 'danger')
            return redirect(url_for('orders'))
        return f(*args, **kwargs)
    return decorated_function

def render_page(content, **kwargs):
    return render_template_string(BASE_TEMPLATE, content=content, **kwargs)

# ============================================
# ===== РОУТЫ =====
# ============================================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('orders'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash(f'Добро пожаловать, {user.username}!', 'success')
            return redirect(url_for('orders'))
        else:
            flash('Неверный email или пароль', 'danger')
    return render_page(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'danger')
            return render_page(REGISTER_TEMPLATE)
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'danger')
            return render_page(REGISTER_TEMPLATE)
        
        if User.query.filter_by(email=email).first():
            flash('Email уже используется', 'danger')
            return render_page(REGISTER_TEMPLATE)
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна! Войдите в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_page(REGISTER_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/orders')
@login_required
def orders():
    return render_page(ORDERS_TEMPLATE)

@app.route('/employee')
@login_required
def employee():
    return render_page(EMPLOYEE_TEMPLATE)

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.all()
    orders = Order.query.all()
    employees = Employee.query.all()
    return render_page(ADMIN_TEMPLATE, users=users, orders=orders, employees=employees)

# ============================================
# ===== API ДЛЯ ЗАКАЗОВ =====
# ============================================

@app.route('/api/orders')
@login_required
def api_orders():
    user_id = session['user_id']
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return jsonify([{
        'id': o.id,
        'order_number': o.order_number,
        'client_name': o.client_name,
        'amount': o.amount,
        'status': o.status,
        'description': o.description,
        'created_at': o.created_at.isoformat()
    } for o in orders])

@app.route('/api/orders', methods=['POST'])
@login_required
def api_create_order():
    data = request.json
    user_id = session['user_id']
    order = Order(
        order_number=data['order_number'],
        client_name=data['client_name'],
        amount=data['amount'],
        status=data.get('status', 'новый'),
        description=data.get('description', ''),
        user_id=user_id
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({'id': order.id, 'message': 'Заказ создан'}), 201

@app.route('/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def api_update_order(order_id):
    data = request.json
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': 'Заказ не найден'}), 404
    order.order_number = data.get('order_number', order.order_number)
    order.client_name = data.get('client_name', order.client_name)
    order.amount = data.get('amount', order.amount)
    order.status = data.get('status', order.status)
    order.description = data.get('description', order.description)
    db.session.commit()
    return jsonify({'message': 'Заказ обновлен'})

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
@login_required
def api_delete_order(order_id):
    user_id = session['user_id']
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': 'Заказ не найден'}), 404
    db.session.delete(order)
    db.session.commit()
    return jsonify({'message': 'Заказ удален'})

# ============================================
# ===== API ДЛЯ СОТРУДНИКОВ =====
# ============================================

@app.route('/api/employees')
@login_required
def api_employees():
    user_id = session['user_id']
    employees = Employee.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'id': e.id,
        'full_name': e.full_name,
        'position': e.position,
        'phone': e.phone,
        'email': e.email,
        'created_at': e.created_at.isoformat()
    } for e in employees])

@app.route('/api/employees', methods=['POST'])
@login_required
def api_create_employee():
    data = request.json
    user_id = session['user_id']
    employee = Employee(
        full_name=data['full_name'],
        position=data['position'],
        phone=data.get('phone', ''),
        email=data.get('email', ''),
        user_id=user_id
    )
    db.session.add(employee)
    db.session.commit()
    return jsonify({'id': employee.id, 'message': 'Сотрудник создан'}), 201

@app.route('/api/employees/<int:employee_id>', methods=['PUT'])
@login_required
def api_update_employee(employee_id):
    data = request.json
    user_id = session['user_id']
    employee = Employee.query.filter_by(id=employee_id, user_id=user_id).first()
    if not employee:
        return jsonify({'error': 'Сотрудник не найден'}), 404
    employee.full_name = data['full_name']
    employee.position = data['position']
    employee.phone = data.get('phone', '')
    employee.email = data.get('email', '')
    db.session.commit()
    return jsonify({'message': 'Сотрудник обновлен'})

@app.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@login_required
def api_delete_employee(employee_id):
    user_id = session['user_id']
    employee = Employee.query.filter_by(id=employee_id, user_id=user_id).first()
    if not employee:
        return jsonify({'error': 'Сотрудник не найден'}), 404
    db.session.delete(employee)
    db.session.commit()
    return jsonify({'message': 'Сотрудник удален'})

# ============================================
# ===== ОБРАБОТКА ОШИБОК =====
# ============================================

@app.errorhandler(404)
def not_found(e):
    return render_page(ERROR_404), 404

@app.errorhandler(500)
def server_error(e):
    return render_page(ERROR_500), 500

# ============================================
# ===== СОЗДАНИЕ ТАБЛИЦ =====
# ============================================

with app.app_context():
    db.create_all()
    print("✅ База данных инициализирована")

# ============================================
# ===== ЗАПУСК =====
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
