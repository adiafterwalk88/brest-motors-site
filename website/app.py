import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "super_secret_flash_key_for_brest_motors"  # Ключ для работы сессий Flask

# ============ ПРЯМОЕ ПОДКЛЮЧЕНИЕ К POSTGRESQL (ИСПРАВЛЕНО!) ============
# Мы исправили опечатку в ID проекта: теперь ophusgconubcufrobzyc
DATABASE_URL = "postgresql://postgres:8026009Wall!@db.ophusgconubcufrobzyc.supabase.co:5432/postgres?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Класс-заглушка (эмулятор), чтобы методы .table().select().execute() не ломались
class SupabaseDirectBackend:
    def table(self, table_name):
        class QueryBuilder:
            def select(self, *args): return self
            def order(self, *args, **kwargs): return self
            def execute(self):
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC;")
                    data = cur.fetchall()
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"⚠️ Ошибка подключения к базе данных: {e}")
                    data = []  # Подстраховка
                
                class Result:
                    def __init__(self, d): self.data = [dict(row) for row in d]
                return Result(data)
        return QueryBuilder()

supabase = SupabaseDirectBackend()

# ============ ДЕКОРАТОР ДЛЯ ЗАЩИТЫ СТРАНИЦ ============
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ============ МАРШРУТЫ (ROUTES) ============

# 1. Главная страница (Дашборд с заказами)
@app.route('/')
@login_required
def dashboard():
    all_orders = supabase.table('orders').select('*').order('id', desc=True).execute().data
    return render_template('dashboard.html', orders=all_orders)

# 2. Страница авторизации (Вход только по ПАРОЛЮ)
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

# 3. Выход из аккаунта
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============ ЗАПУСК ПРИЛОЖЕНИЯ ============
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
