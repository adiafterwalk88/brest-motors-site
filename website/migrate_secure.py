#!/usr/bin/env python3
"""
Миграция базы данных с добавлением полей для безопасности
Запуск: python migrate_secure.py
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ Ошибка: Переменная DATABASE_URL не найдена в файле .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("🔄 Начинаем миграцию безопасности (Soft Delete & Audit Logs)...")
        
        # 1. Добавляем поле deleted_at для мягкого удаления
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;")
        print("✅ Поле deleted_at проверено/добавлено")
        
        # 2. Частичный индекс для быстрых выборок НЕУДАЛЕННЫХ заказов (оптимизация performance)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_active 
            ON orders(id) 
            WHERE deleted_at IS NULL;
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_deleted_at ON orders(deleted_at);")
        print("✅ Созданы индексы для мягкого удаления")
        
        # 3. Таблица аудит-логов (Audit Log)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50),
                user_name VARCHAR(100),
                action VARCHAR(50),
                target_type VARCHAR(50),
                target_id INTEGER,
                details JSONB,
                ip_address VARCHAR(45),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✅ Таблица audit_logs проверена/создана")
        
        # 4. Индексы для таблицы audit_logs
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs(target_type, target_id);")
        print("✅ Созданы индексы для аудит-логов")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\n🎉 Миграция безопасности успешно завершена!")
        print("   • Мягкое удаление (deleted_at) готово к работе")
        print("   • Таблица audit_logs готова для записи событий")
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")

if __name__ == '__main__':
    migrate()
