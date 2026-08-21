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
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        
        print("🔄 Миграция базы данных (безопасность)...")
        
        # 1. Добавляем deleted_at для мягкого удаления
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='deleted_at') THEN
                    ALTER TABLE orders ADD COLUMN deleted_at TIMESTAMP;
                END IF;
            END $$;
        """)
        print("✅ Добавлено поле deleted_at (мягкое удаление)")
        
        # 2. Индекс для deleted_at
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_deleted_at ON orders(deleted_at);")
        print("✅ Создан индекс idx_orders_deleted_at")
        
        # 3. Таблица для audit-логов
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
        print("✅ Создана таблица audit_logs")
        
        # 4. Индексы для audit_logs
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);")
        print("✅ Созданы индексы для audit_logs")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\n🎉 Миграция завершена!")
        print("  ✅ Добавлено мягкое удаление (deleted_at)")
        print("  ✅ Создана таблица audit_logs для логирования")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    migrate()
