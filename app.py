import os
import secrets
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client
from datetime import datetime, timedelta
from functools import wraps
import bcrypt

# ===== Инициализация приложения =====
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ============================================
# ===== ПОДКЛЮЧЕНИЕ К SUPABASE =====
# ============================================
SUPABASE_URL = "https://ophusgconubcufrobzyc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9waHVzZ2NvbnViY3Vmcm9ienljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM1ODc5MjQsImV4cCI6MjA5OTE2MzkyNH0.a1DBm4PkDt1NHHyIDfF_xFqZd7qEhSGwUfdZbnvXKXs"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Подключение к Supabase установлено!")

# ============================================
# ===== ДАННЫЕ =====
# ============================================

STORES = [
    {'id': 1, 'name': 'Магазин Карьерная', 'executors': ['Павел Иванович', 'Александр']},
    {'id': 2, 'name': 'Магазин Московская', 'executors': ['Паша', 'Дмитрий']}
]

# ============================================
# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
# ============================================

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

def get_store_executors(store_id):
    for s in STORES:
        if s['id'] == store_id:
            return s['executors']
    return []

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
        try:
            user = supabase.table('users').select('*').eq('id', session['user_id']).execute()
            if not user.data or not user.data[0].get('is_admin', False):
                flash('Доступ запрещен', 'danger')
                return redirect(url_for('orders'))
        except:
            flash('Ошибка доступа', 'danger')
            return redirect(url_for('orders'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# ===== ШАБЛОНЫ =====
# ============================================

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
        .header nav a { color: rgba(255,255,255,0.8); text-decoration: none; padding: 5px 10px; border-radius: 4px; font-size: 14px
