import os
import logging
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

from flask import (
    Flask, render_template, request, jsonify, flash, redirect,
    url_for, session
)
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf import CSRFProtect
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.DEBUG if os.environ.get('FLASK_DEBUG', 'False') == 'True' else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('brest_motors')

app = Flask(__name__)

# ---------- КРИТИЧЕСКИЙ ФИКС #1: SECRET_KEY ----------
# Раньше был статический дефолт 'default-secret-key-for-dev', известный
# любому, кто видел этот файл — это позволяет подделывать сессии (session
# forgery). Теперь: в бою SECRET_KEY обязателен, в деве — предупреждаем
# и генерируем случайный (сессии просто слетят при рестарте, это ок для dev).
_debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if _debug_mode:
        _secret_key = os.urandom(32).hex()
        logger.warning(
            "SECRET_KEY не задан в .env — сгенерирован случайный ключ на время "
            "этого запуска (сессии обнулятся при рестарте). Это ДОПУСТИМО только "
            "в разработке. Перед деплоем в прод задайте постоянный SECRET_KEY в .env."
        )
    else:
        raise RuntimeError(
            "SECRET_KEY не задан. В production-режиме (FLASK_DEBUG=False) "
            "запуск без постоянного SECRET_KEY запрещён — иначе сессии всех "
            "пользователей можно подделать. Сгенерируйте: python -c "
            "\"import os; print(os.urandom(32).hex())\" и добавьте в .env."
        )
app.secret_key = _secret_key


class Config:
    DATABASE_URL = os.environ.get('DATABASE_URL')
    DEBUG = _debug_mode
    SHOPS = {
        'all': 'Все филиалы',
        'moskovskaya': '🏪 ул. Московская, 123',
        'kariernaya': '🏪 ул. Карьерная, 45'
    }
    # Список используется только для выпадающих списков "исполнитель" —
    # реальные учётки логина живут в таблице users (см. migrate_users.py)
    EMPLOYEES = ['Павел Иванович', 'Павел', 'Дмитрий', 'Александр']


app.config.from_object(Config)

if not Config.DATABASE_URL:
    raise RuntimeError("DATABASE_URL не найден в .env")

if not Config.DATABASE_URL.startswith('postgresql://') and not Config.DATABASE_URL.startswith('postgres://'):
    # ---------- КРИТИЧЕСКИЙ ФИКС: несовместимость драйвера и строки подключения ----------
    # Это приложение написано на psycopg2 (Postgres-драйвер). Строка вида
    # sqlite:///brest_motors.db физически не подключится через psycopg2 —
    # получите TypeError/OperationalError при первом же запросе к БД.
    # Если вам реально нужен SQLite — это не однострочный фикс, а замена
    # слоя доступа к данным (psycopg2 → sqlite3 или SQLAlchemy с двумя
    # диалектами), сам собой это не чинится. Здесь просто останавливаем
    # запуск с понятной ошибкой вместо непонятного падения на первом запросе.
    raise RuntimeError(
        "DATABASE_URL должен начинаться с 'postgresql://' — этот код использует "
        "psycopg2 и не умеет работать с SQLite. Если нужен SQLite для локальной "
        "разработки, это отдельная задача (замена db-слоя), а не опечатка в .env."
    )

# ---------- CSRF-защита (в версии B отсутствовала полностью) ----------
csrf = CSRFProtect(app)

db_pool = None


def init_db_pool():
    global db_pool
    if db_pool is not None:
        return
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=10, dsn=Config.DATABASE_URL
        )
        logger.info("Пул соединений PostgreSQL создан")
    except Exception:
        logger.exception("Ошибка подключения к PostgreSQL")
        raise


@contextmanager
def get_db_cursor(commit=False):
    if db_pool is None:
        init_db_pool()
    conn = db_pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка выполнения БД-запроса")
        raise
    finally:
        cur.close()
        db_pool.putconn(conn)


def normalize_order(order):
    """Приводит ключи словаря заказа к единому виду для шаблонов."""
    if not order:
        return order
    d = dict(order)
    d['customer_name'] = d.get('customer_name') or ''
    d['customer_phone'] = d.get('customer_phone') or ''
    d['device_model'] = d.get('device_model') or ''
    d['device_type'] = d.get('device_type') or ''
    d['executor'] = d.get('executor') or 'Не назначен'
    d['estimated_cost'] = d.get('estimated_cost') or 0
    d['prepayment'] = d.get('prepayment') or 0
    d['status'] = d.get('status') or 'Принят'
    return d


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('orders_page'))
        return f(*args, **kwargs)
    return decorated


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if not Config.DEBUG:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def create_notification(user_id, user_name, title, message, order_id=None,
                         priority='Обычный', action_url=None):
    """Создаёт уведомление, если такое же (по order_id+title) ещё не существует
    за последние 24 часа — чтобы не заспамить дубликатами при каждом опросе."""
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                SELECT id FROM notifications
                WHERE user_id = %s AND title = %s AND order_id IS NOT DISTINCT FROM %s
                  AND created_at > NOW() - INTERVAL '24 hours';
            """, (user_id, title, order_id))
            if cur.fetchone():
                return
            cur.execute("""
                INSERT INTO notifications
                    (user_id, user_name, title, message, order_id, priority, action_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (user_id, user_name, title, message, order_id, priority, action_url))
    except Exception:
        logger.exception("Не удалось создать уведомление")


# ==========================================
# АВТОРИЗАЦИЯ
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('orders_page'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if not username or not password:
            flash('Введите логин и пароль', 'error')
            return render_template('login.html')
        try:
            with get_db_cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
                user = cur.fetchone()
                if user and check_password_hash(user['password_hash'], password):
                    session.clear()
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['user_name'] = user.get('display_name') or user['username']
                    session['is_admin'] = bool(user.get('is_admin'))
                    session['shop_id'] = 'all'
                    flash(f"✅ Добро пожаловать, {session['user_name']}!", 'success')
                    return redirect(url_for('orders_page'))
                else:
                    flash('Неверное имя пользователя или пароль', 'error')
        except Exception:
            logger.exception("Ошибка входа")
            flash('Ошибка входа. Попробуйте позже.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/set-shop/<shop_id>')
@login_required
def set_shop(shop_id):
    if shop_id in Config.SHOPS or shop_id == 'all':
        session['shop_id'] = shop_id
        flash(f"🔄 Переключено на {Config.SHOPS.get(shop_id, shop_id)}", 'success')
    return redirect(request.referrer or url_for('orders_page'))


# ==========================================
# ДАШБОРД / ЗАКАЗЫ
# ==========================================

@app.route('/')
@login_required
def dashboard():
    return redirect(url_for('orders_page'))


@app.route('/orders')
@login_required
def orders_page():
    try:
        shop_id = session.get('shop_id', 'all')
        show_archived = request.args.get('show_archived', 'false') == 'true'
        search = request.args.get('search', '').strip()

        with get_db_cursor() as cur:
            query = "SELECT * FROM orders WHERE deleted_at IS NULL"
            params = []

            if shop_id != 'all' and shop_id:
                query += " AND (shop_id = %s OR shop_id IS NULL)"
                params.append(shop_id)

            if not show_archived:
                query += " AND (is_archived = FALSE OR is_archived IS NULL)"

            if search:
                query += " AND (customer_name ILIKE %s OR customer_phone ILIKE %s OR device_model ILIKE %s)"
                term = f"%{search}%"
                params.extend([term, term, term])

            query += " ORDER BY created_at DESC;"
            cur.execute(query, tuple(params))
            orders = [normalize_order(o) for o in cur.fetchall()]

            cur.execute("SELECT COUNT(*) AS count FROM orders WHERE is_archived = TRUE AND deleted_at IS NULL;")
            archived_count = cur.fetchone()['count']

        return render_template(
            'orders.html',
            orders=orders,
            search=search,
            show_archived=show_archived,
            archived_count=archived_count,
            shops=Config.SHOPS,
            total_count=len(orders),
            active_page='orders'
        )
    except Exception:
        logger.exception("Ошибка загрузки заказов")
        flash('Ошибка загрузки заказов', 'error')
        return render_template('orders.html', orders=[], shops=Config.SHOPS,
                                active_page='orders', total_count=0, archived_count=0,
                                search='', show_archived=False)


@app.route('/order/new', methods=['GET', 'POST'])
@login_required
def new_order():
    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('customer_name', '').strip() or not data.get('customer_phone', '').strip():
                flash('Имя клиента и телефон обязательны', 'error')
                return render_template('order_form.html', employees=Config.EMPLOYEES, shops=Config.SHOPS)

            shop_id = session.get('shop_id')
            if shop_id == 'all' or not shop_id:
                shop_id = 'moskovskaya'

            with get_db_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO orders (
                        customer_name, customer_phone, device_type, device_model,
                        serial_number, defect_description, estimated_cost,
                        prepayment, executor, status, shop_id, created_by, created_at, is_archived
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), FALSE)
                    RETURNING id;
                """, (
                    data.get('customer_name', '').strip(),
                    data.get('customer_phone', '').strip(),
                    data.get('device_type', '').strip(),
                    data.get('device_model', '').strip(),
                    data.get('serial_number', '').strip(),
                    data.get('defect_description', '').strip(),
                    data.get('estimated_cost') or 0,
                    data.get('prepayment') or 0,
                    data.get('executor') or 'Не назначен',
                    data.get('status', 'Принят'),
                    shop_id,
                    session.get('user_name')
                ))
                order_id = cur.fetchone()['id']
                flash(f'✅ Заказ #{order_id} успешно создан!', 'success')
                return redirect(url_for('orders_page'))
        except Exception:
            logger.exception("Ошибка при создании заказа")
            flash('Ошибка при создании заказа', 'error')

    return render_template('order_form.html', employees=Config.EMPLOYEES, shops=Config.SHOPS)


@app.route('/orders/<int:order_id>/edit', methods=['GET'])
@login_required
def edit_order_form(order_id):
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s AND deleted_at IS NULL;", (order_id,))
            order = cur.fetchone()
        if not order:
            flash('Заказ не найден', 'error')
            return redirect(url_for('orders_page'))
        return render_template('edit_order.html', order=normalize_order(order),
                                shops=Config.SHOPS, employees=Config.EMPLOYEES,
                                active_page='orders')
    except Exception:
        logger.exception("Ошибка загрузки заказа")
        flash('Ошибка загрузки заказа', 'error')
        return redirect(url_for('orders_page'))


@app.route('/orders/<int:order_id>/edit', methods=['POST'])
@login_required
def edit_order(order_id):
    try:
        data = request.form
        if not data.get('customer', '').strip() or not data.get('phone', '').strip():
            flash('Имя клиента и телефон обязательны', 'error')
            return redirect(url_for('edit_order_form', order_id=order_id))

        with get_db_cursor(commit=True) as cur:
            cur.execute("SELECT id FROM orders WHERE id = %s AND deleted_at IS NULL;", (order_id,))
            if not cur.fetchone():
                flash('Заказ не найден', 'error')
                return redirect(url_for('orders_page'))

            cur.execute("""
                UPDATE orders SET
                    customer_name = %s, customer_phone = %s, defect_description = %s,
                    estimated_cost = %s, prepayment = %s, executor = %s, status = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (
                data.get('customer', '').strip(),
                data.get('phone', '').strip(),
                data.get('product', '').strip(),
                data.get('price') or 0,
                data.get('prepaid') or 0,
                data.get('executor') or 'Не назначен',
                data.get('status') or 'Принят',
                order_id
            ))
        flash(f'✅ Заказ #{order_id} обновлён!', 'success')
        return redirect(url_for('orders_page'))
    except Exception:
        logger.exception("Ошибка редактирования заказа")
        flash('Ошибка при сохранении', 'error')
        return redirect(url_for('orders_page'))


@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_order(order_id):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("UPDATE orders SET deleted_at = NOW() WHERE id = %s;", (order_id,))
        flash(f'🗑️ Заказ #{order_id} удалён', 'success')
    except Exception:
        logger.exception("Ошибка удаления заказа")
        flash('Ошибка при удалении', 'error')
    return redirect(url_for('orders_page'))


@app.route('/orders/<int:order_id>/complete', methods=['POST'])
@login_required
def complete_order(order_id):
    try:
        notes = request.form.get('notes', '').strip()
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE orders SET status = 'Выдан', completed_at = NOW(),
                       employee_notes = %s, updated_at = NOW()
                WHERE id = %s;
            """, (notes, order_id))
        flash(f'✅ Заказ #{order_id} завершён', 'success')
    except Exception:
        logger.exception("Ошибка завершения заказа")
        flash('Ошибка при завершении заказа', 'error')
    return redirect(request.referrer or url_for('employee_dashboard'))


# ==========================================
# КЛИЕНТЫ
# ==========================================

@app.route('/clients')
@login_required
def clients_page():
    try:
        search = request.args.get('q', '').strip()
        with get_db_cursor() as cur:
            query = """
                SELECT customer_name, customer_phone,
                       COUNT(*) AS orders_count,
                       COALESCE(SUM(estimated_cost), 0) AS total_spent,
                       STRING_AGG(DISTINCT shop_id, ', ') AS stores
                FROM orders
                WHERE customer_name IS NOT NULL AND customer_name != '' AND deleted_at IS NULL
            """
            params = []
            if search:
                query += " AND (customer_name ILIKE %s OR customer_phone ILIKE %s)"
                params.extend([f"%{search}%", f"%{search}%"])
            query += " GROUP BY customer_name, customer_phone ORDER BY customer_name;"
            cur.execute(query, tuple(params))
            clients = cur.fetchall()
        return render_template('clients.html', clients=clients, active_page='clients')
    except Exception:
        logger.exception("Ошибка загрузки клиентов")
        return render_template('clients.html', clients=[], active_page='clients')


# ==========================================
# КАБИНЕТ СОТРУДНИКА
# ==========================================

@app.route('/employee')
@login_required
def employee_dashboard():
    user_name = session.get('user_name')
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status != 'Выдан') AS active,
                    COUNT(*) FILTER (WHERE status = 'Выдан' AND completed_at::date = CURRENT_DATE) AS completed_today,
                    COUNT(*) FILTER (WHERE status = 'Принят') AS new_orders
                FROM orders
                WHERE executor = %s AND deleted_at IS NULL;
            """, (user_name,))
            my_stats = cur.fetchone()

            cur.execute("""
                SELECT * FROM orders
                WHERE executor = %s AND status != 'Выдан' AND deleted_at IS NULL
                ORDER BY created_at DESC;
            """, (user_name,))
            my_orders = [normalize_order(o) for o in cur.fetchall()]

            orders_by_shop = {}
            for shop_id, shop_name in Config.SHOPS.items():
                if shop_id == 'all':
                    continue
                cur.execute("""
                    SELECT * FROM orders
                    WHERE shop_id = %s AND status != 'Выдан' AND deleted_at IS NULL
                    ORDER BY created_at DESC;
                """, (shop_id,))
                active_orders = [normalize_order(o) for o in cur.fetchall()]
                orders_by_shop[shop_id] = {
                    'name': shop_name,
                    'active_orders': active_orders,
                    'stats': {
                        'active': len(active_orders),
                        'my_active': sum(1 for o in active_orders if o['executor'] == user_name)
                    }
                }

        return render_template('employee_dashboard.html',
                                my_stats=my_stats, my_orders=my_orders,
                                orders_by_shop=orders_by_shop, today_tasks=[],
                                shops=Config.SHOPS, active_page='employee')
    except Exception:
        logger.exception("Ошибка кабинета сотрудника")
        flash('Ошибка загрузки данных', 'error')
        return render_template('employee_dashboard.html', my_stats=None, my_orders=[],
                                orders_by_shop={}, today_tasks=[], shops=Config.SHOPS,
                                active_page='employee')


@app.route('/employee/orders/create', methods=['GET', 'POST'])
@login_required
def employee_create_order():
    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('customer', '').strip() or not data.get('phone', '').strip() or not data.get('product', '').strip():
                flash('Заполните все обязательные поля', 'error')
                return redirect(url_for('employee_create_order'))

            shop_id = data.get('shop_id') or 'moskovskaya'
            with get_db_cursor(commit=True) as cur:
                cur.execute("""
                    INSERT INTO orders (
                        customer_name, customer_phone, address, defect_description,
                        estimated_cost, prepayment, priority, executor, status,
                        comment, shop_id, created_by, created_at, is_archived
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Принят', %s, %s, %s, NOW(), FALSE)
                    RETURNING id;
                """, (
                    data.get('customer').strip(), data.get('phone').strip(),
                    data.get('address', '').strip(), data.get('product').strip(),
                    data.get('price') or 0, data.get('prepaid') or 0,
                    data.get('priority') or 'Обычный', session.get('user_name'),
                    data.get('comment', '').strip(), shop_id, session.get('user_name')
                ))
                order_id = cur.fetchone()['id']
            flash(f'✅ Заказ #{order_id} создан!', 'success')
            return redirect(url_for('employee_dashboard'))
        except Exception:
            logger.exception("Ошибка создания заказа сотрудником")
            flash('Ошибка при создании заказа', 'error')

    return render_template('employee_create_order.html', shops=Config.SHOPS,
                            user_name=session.get('user_name'), active_page='employee')


@app.route('/employee/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def employee_edit_order(order_id):
    user_name = session.get('user_name')
    try:
        with get_db_cursor(commit=(request.method == 'POST')) as cur:
            cur.execute("SELECT * FROM orders WHERE id = %s AND deleted_at IS NULL;", (order_id,))
            order = cur.fetchone()
            if not order:
                flash('Заказ не найден', 'error')
                return redirect(url_for('employee_dashboard'))
            if order.get('executor') != user_name and not session.get('is_admin'):
                flash('Вы не назначены исполнителем этого заказа', 'error')
                return redirect(url_for('employee_dashboard'))

            if request.method == 'POST':
                data = request.form
                cur.execute("""
                    UPDATE orders SET
                        customer_name = %s, customer_phone = %s, address = %s,
                        defect_description = %s, estimated_cost = %s, prepayment = %s,
                        priority = %s, status = %s, comment = %s, updated_at = NOW()
                    WHERE id = %s;
                """, (
                    data.get('customer', '').strip(), data.get('phone', '').strip(),
                    data.get('address', '').strip(), data.get('product', '').strip(),
                    data.get('price') or 0, data.get('prepaid') or 0,
                    data.get('priority') or 'Обычный', data.get('status') or 'Принят',
                    data.get('comment', '').strip(), order_id
                ))
                flash(f'✅ Заказ #{order_id} обновлён!', 'success')
                return redirect(url_for('employee_dashboard'))

        return render_template('employee_edit_order.html', order=normalize_order(order),
                                user_name=user_name, shops=Config.SHOPS, active_page='employee')
    except Exception:
        logger.exception("Ошибка редактирования заказа сотрудником")
        flash('Ошибка при сохранении', 'error')
        return redirect(url_for('employee_dashboard'))


# ==========================================
# ЧАТ
# ==========================================

@app.route('/chat')
@login_required
def chat_page():
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT 50;")
            chat_messages = list(reversed(cur.fetchall()))
        return render_template('chat.html', chat_messages=chat_messages, active_page='chat')
    except Exception:
        logger.exception("Ошибка загрузки чата")
        return render_template('chat.html', chat_messages=[], active_page='chat')


@app.route('/api/chat/send', methods=['POST'])
@login_required
def api_chat_send():
    message = (request.form.get('message') or (request.get_json(silent=True) or {}).get('message') or '').strip()
    if not message:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Пустое сообщение'}), 400
        flash('Сообщение не может быть пустым', 'error')
        return redirect(url_for('chat_page'))

    if len(message) > 2000:
        message = message[:2000]

    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                INSERT INTO chat_messages (user_id, user_name, message)
                VALUES (%s, %s, %s) RETURNING id, created_at;
            """, (session.get('user_id'), session.get('user_name'), message))
            row = cur.fetchone()
        if request.is_json:
            return jsonify({'success': True, 'id': row['id']})
        return redirect(url_for('chat_page'))
    except Exception:
        logger.exception("Ошибка отправки сообщения в чат")
        if request.is_json:
            return jsonify({'success': False, 'error': 'Ошибка отправки'}), 500
        flash('Ошибка отправки сообщения', 'error')
        return redirect(url_for('chat_page'))


@app.route('/api/chat/messages')
@login_required
def api_chat_messages():
    limit = min(request.args.get('limit', 50, type=int), 200)
    after_id = request.args.get('after', type=int)
    try:
        with get_db_cursor() as cur:
            if after_id:
                cur.execute("""
                    SELECT * FROM chat_messages WHERE id > %s
                    ORDER BY created_at ASC LIMIT %s;
                """, (after_id, limit))
            else:
                cur.execute("SELECT * FROM chat_messages ORDER BY created_at DESC LIMIT %s;", (limit,))
            rows = cur.fetchall()
            if not after_id:
                rows = list(reversed(rows))
        return jsonify([{
            'id': r['id'], 'user_name': r['user_name'], 'message': r['message'],
            'created_at': r['created_at'].isoformat()
        } for r in rows])
    except Exception:
        logger.exception("Ошибка получения сообщений чата")
        return jsonify([])


# ==========================================
# КАЛЕНДАРЬ
# ==========================================

@app.route('/calendar')
@login_required
def calendar_page():
    return render_template('calendar.html', active_page='calendar')


@app.route('/api/calendar/events')
@login_required
def api_calendar_events():
    """События календаря = заказы с датой создания, цвет по статусу."""
    colors = {'Принят': '#3b82f6', 'В работе': '#f59e0b', 'Выдан': '#10b981'}
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT id, customer_name, device_model, status, executor, created_at
                FROM orders WHERE deleted_at IS NULL
                ORDER BY created_at DESC LIMIT 300;
            """)
            orders = cur.fetchall()
        events = [{
            'id': o['id'],
            'title': f"#{o['id']} {o['customer_name']}",
            'start': o['created_at'].date().isoformat() if o['created_at'] else None,
            'color': colors.get(o['status'], '#6b7280'),
            'extendedProps': {
                'order_id': o['id'], 'customer': o['customer_name'],
                'product': o['device_model'], 'status': o['status'],
                'executor': o['executor']
            }
        } for o in orders if o['created_at']]
        return jsonify(events)
    except Exception:
        logger.exception("Ошибка загрузки событий календаря")
        return jsonify([])


# ==========================================
# УВЕДОМЛЕНИЯ
# ==========================================

@app.route('/notifications')
@login_required
def notifications_page():
    filter_type = request.args.get('type', 'all')
    user_id = session.get('user_id')
    try:
        with get_db_cursor() as cur:
            query = "SELECT * FROM notifications WHERE user_id = %s"
            params = [user_id]
            if filter_type == 'unread':
                query += " AND is_read = FALSE AND is_archived = FALSE"
            elif filter_type == 'read':
                query += " AND is_read = TRUE AND is_archived = FALSE"
            elif filter_type == 'archived':
                query += " AND is_archived = TRUE"
            else:
                query += " AND is_archived = FALSE"
            query += " ORDER BY created_at DESC LIMIT 100;"
            cur.execute(query, tuple(params))
            notifications = cur.fetchall()

            cur.execute("""
                SELECT COUNT(*) AS unread FROM notifications
                WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE;
            """, (user_id,))
            stats = cur.fetchone()

        return render_template('notifications.html', notifications=notifications,
                                filter_type=filter_type, stats=stats, active_page='notifications')
    except Exception:
        logger.exception("Ошибка загрузки уведомлений")
        return render_template('notifications.html', notifications=[], filter_type=filter_type,
                                stats={'unread': 0}, active_page='notifications')


@app.route('/api/notifications/check')
@login_required
def api_notifications_check():
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS c FROM orders
                WHERE executor = %s AND status = 'Принят' AND deleted_at IS NULL;
            """, (user_name,))
            new_orders = cur.fetchone()['c']

            cur.execute("""
                SELECT COUNT(*) AS c FROM notifications
                WHERE user_id = %s AND is_read = FALSE AND is_archived = FALSE;
            """, (user_id,))
            unread = cur.fetchone()['c']

            cur.execute("""
                SELECT id, customer_name, created_at FROM orders
                WHERE executor = %s AND status != 'Выдан' AND deleted_at IS NULL;
            """, (user_name,))
            active_orders = cur.fetchall()

        overdue_ids = []
        for o in active_orders:
            if o['created_at'] and datetime.now() - o['created_at'].replace(tzinfo=None) > timedelta(hours=48):
                overdue_ids.append(o['id'])
                create_notification(
                    user_id=user_id, user_name=user_name,
                    title=f"⚠️ Заказ #{o['id']} просрочен!",
                    message=f"Заказ для {o['customer_name']} создан более 48 часов назад",
                    order_id=o['id'], priority='Высокий', action_url='/orders'
                )

        return jsonify({'new_orders': new_orders, 'unread': unread,
                         'overdue': len(overdue_ids), 'overdue_ids': overdue_ids})
    except Exception:
        logger.exception("Ошибка проверки уведомлений")
        return jsonify({'new_orders': 0, 'unread': 0, 'overdue': 0, 'overdue_ids': []})


@app.route('/api/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def api_notification_mark_read(notif_id):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE notifications SET is_read = TRUE
                WHERE id = %s AND user_id = %s;
            """, (notif_id, session.get('user_id')))
        return jsonify({'success': True})
    except Exception:
        logger.exception("Ошибка отметки уведомления как прочитанного")
        return jsonify({'success': False}), 500


@app.route('/api/notifications/archive/<int:notif_id>', methods=['POST'])
@login_required
def api_notification_archive(notif_id):
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE notifications SET is_archived = TRUE
                WHERE id = %s AND user_id = %s;
            """, (notif_id, session.get('user_id')))
        return jsonify({'success': True})
    except Exception:
        logger.exception("Ошибка архивации уведомления")
        return jsonify({'success': False}), 500


@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def api_notifications_mark_all_read():
    try:
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                UPDATE notifications SET is_read = TRUE
                WHERE user_id = %s AND is_read = FALSE;
            """, (session.get('user_id'),))
        return jsonify({'success': True})
    except Exception:
        logger.exception("Ошибка массовой отметки уведомлений")
        return jsonify({'success': False}), 500


# ==========================================
# ЗАПУСК
# ==========================================

init_db_pool()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # ---------- КРИТИЧЕСКИЙ ФИКС: debug=True больше не захардкожен ----------
    # Было: app.run(host='0.0.0.0', port=port, debug=True) — это включало
    # интерактивный Werkzeug-дебаггер безусловно, даже в проде. Дебаггер
    # позволяет выполнять произвольный Python-код через браузер при любом
    # необработанном исключении — это RCE (remote code execution) "из коробки".
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
