#!/usr/bin/env python3
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate_database():
    """Обновление структуры базы данных"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ Ошибка: DATABASE_URL не найдена в переменных окружения.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("🔄 Начинаем миграцию базы данных...")
        
        # 1. Добавляем колонки напрямую с помощью ADD COLUMN IF NOT EXISTS
        columns_to_add = [
            ("completed_at", "TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("employee_notes", "TEXT"),
            ("created_by", "VARCHAR(255) DEFAULT 'system'"),
            ("executor_id", "VARCHAR(255)"),
            ("shop_id", "VARCHAR(50) DEFAULT 'moskovskaya'"),
            ("is_archived", "BOOLEAN DEFAULT FALSE")
        ]
        
        for col_name, col_type in columns_to_add:
            cur.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
            print(f"✅ Проверена/добавлена колонка {col_name}")

        # 2. Создаем таблицу чата
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                user_name VARCHAR(100) NOT NULL,
                user_role VARCHAR(50),
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✅ Проверена/создана таблица chat_messages")
        
        # 3. Создаем индексы для ускорения выборок
        indexes = [
            ("idx_chat_messages_created_at", "chat_messages(created_at DESC)"),
            ("idx_orders_completed_at", "orders(completed_at)"),
            ("idx_orders_created_by", "orders(created_by)"),
            ("idx_orders_executor_id", "orders(executor_id)"),
            ("idx_orders_executor_status", "orders(executor, status)"),
            ("idx_orders_updated_at", "orders(updated_at)")
        ]
        
        for idx_name, idx_def in indexes:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def};")
        print("✅ Созданы/проверены индексы")
        
        # 4. Безопасное заполнение NULL значений
        cur.execute("UPDATE orders SET created_by = 'system' WHERE created_by IS NULL;")
        cur.execute("UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;")
        print("✅ Обновлены значение по умолчанию для существующих записей")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\n🎉 Миграция завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

def check_database_structure():
    """Проверка текущей структуры базы данных"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("\n📊 Текущие колонки таблицы orders:")
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'orders'
            ORDER BY ordinal_position;
        """)
        for col in cur.fetchall():
            print(f"  • {col[0]}: {col[1]} (nullable: {col[2]})")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")

if __name__ == '__main__':
    print("=" * 50)
    print("🛠️  УТИЛИТА МИГРАЦИИ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    check_database_structure()
    print("\n" + "=" * 50)
    migrate_database()
    print("\n" + "=" * 50)
    check_database_structure()
