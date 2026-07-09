import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super_secret_flash_key_for_brest_motors"

# Добавляем hasattr в контекст шаблонизатора Jinja2 для проверки даты
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
                    # Сортируем по ID по возрастанию, чтобы метод [-10:]|reverse в шаблоне брал последние добавленные
                    cur.execute(f"SELECT * FROM {table_name} ORDER BY id ASC;")
                    data = cur.fetchall()
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"⚠️ Ошибка подключения к базе {table_name}: {e}")
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

# ============ МАРШРУТЫ ============

@app.route('/')
@app.route('/orders')
@login_required
def dashboard():
    all_orders = supabase.table('orders').select('*').execute().data
    
    # 1. Расчет базовых показателей
    all_count = len(all_orders)
    active_count = sum(1 for o in all_orders if o.get('status') in ['Новый', 'В работе', 'Готов'])
    
    # Расчет созданных за сегодня
    today_str = datetime.today().strftime('%Y-%m-%d')
    today_count = 0
    for o in all_orders:
        created = o.get('created_at')
        if created:
            created_str = created.strftime('%Y-%m-%d') if hasattr(created, 'strftime') else str(created)
            if created_str.startswith(today_str):
                today_count += 1
                
    # Суммы оборота и остатка к оплате (Общая стоимость минус то, что уже внесли)
    total_sum = sum(float(o.get('price') or 0) for o in all_orders)
    
    # Дебиторка/остаток: общая сумма незавершенных заказов за вычетом предоплаты
    debt = sum(float(o.get('price') or 0) - float(o.get('prepaid') or 0) 
               for o in all_orders if o.get('status') != 'Завершен')

    # 2. Динамический расчет статистики исполнителей
    exec_stats = {}
    for o in all_orders:
        executor = o.get('executor') or 'Не назначен'
        price = float(o.get('price') or 0)
        if executor not in exec_stats:
            exec_stats[executor] = {'count': 0, 'sum': 0.0}
        exec_stats[executor]['count'] += 1
        exec_stats[executor]['sum'] += price
        
    # Преобразуем суммы мастеров к целому числу для красоты
    for ex in exec_stats:
        exec_stats[ex]['sum'] = int(exec_stats[ex]['sum'])

    return render_template(
        'dashboard.html', 
        orders=all_orders, 
        current_page='dashboard',
        all_count=all_count,
        active_count=active_count,
        today_count=today_count,
        total_sum=int(total_sum),
        debt=int(max(0, debt)), # исключаем отрицательные значения
        exec_stats=exec_stats
    )

@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
        # Забираем абсолютно все поля формы
        customer = request.form.get('customer')
        phone = request.form.get('phone')
        address = request.form.get('address')
        product = request.form.get('product')
        price = request.form.get('price') or 0
        prepaid = request.form.get('prepaid') or 0
        priority = request.form.get('priority') or 'Обычный'
        executor = request.form.get('executor') or 'Не назначен'
        status = request.form.get('status') or 'Новый'
        comment = request.form.get('comment')
        source = request.form.get('source') or 'Сайт'

        # Прямая параметризованная вставка в PostgreSQL
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            query = """
                INSERT INTO orders (customer, phone, address, product, price, prepaid, priority, executor, status, comment, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """
            cur.execute(query, (customer, phone, address, product, price, prepaid, priority, executor, status, comment, source))
            conn.commit()
            cur.close()
            conn.close()
            print("[DB] Заказ успешно сохранен со всеми дополнительными параметрами!")
        except Exception as e:
            print(f"[DB] Ошибка при сохранении заказа: {e}")

        return redirect(url_for('dashboard'))

    return render_template('dashboard.html', current_page='create_order', orders=[], exec_stats={})

@app.route('/clients')
@login_required
def clients():
    all_clients = supabase.table('clients').select('*').execute().data
    try:
        return render_template('clients.html', clients=all_clients, current_page='clients', exec_stats={})
    except Exception:
        return render_template('dashboard.html', clients=all_clients, orders=[], current_page='clients', exec_stats={})

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == '8026009Wall!':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = 'Неверный пароль доступа'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
