import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def fix_database():
    """Исправление и обновление структуры базы данных"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ Ошибка: Переменная окружения DATABASE_URL не найдена!")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        print("🔄 Исправляем структуру БД...")
        
        # 1. Добавляем необходимые колонки в таблицу orders
        # PostgreSQL поддерживает ADD COLUMN IF NOT EXISTS начиная с версии 9.6
        columns_to_add = [
            ("shop_id", "VARCHAR(50) DEFAULT 'moskovskaya'"),
            ("is_archived", "BOOLEAN DEFAULT FALSE"),
            ("completed_at", "TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("employee_notes", "TEXT")
        ]
        
        for col_name, col_def in columns_to_add:
            cur.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
            print(f"  └─ Колонка {col_name}: проверена/добавлена")
            
        # 2. Заполняем NULL значения для существующих записей
        cur.execute("UPDATE orders SET shop_id = 'moskovskaya' WHERE shop_id IS NULL;")
        cur.execute("UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;")
        print("✅ Заполнены базовые значения по умолчанию")
        
        # 3. Создаем индексы для ускорения выборок и фильтрации
        indexes = [
            ("idx_orders_shop_id", "orders(shop_id)"),
            ("idx_orders_is_archived", "orders(is_archived)"),
            ("idx_orders_completed_at", "orders(completed_at)"),
            ("idx_orders_status", "orders(status)"),
            ("idx_orders_executor", "orders(executor)")
        ]
        
        for idx_name, idx_def in indexes:
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def};")
            
        print("✅ Индексы успешно проверены/созданы")
        
        # 4. Создаем таблицу чата
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                user_name VARCHAR(100) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✅ Таблица chat_messages проверена/создана")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("\n🎉 База данных успешно обновлена!")
        print("    • Добавлена отсутствовавшая колонка updated_at")
        print("    • Добавлены колонки shop_id, is_archived, completed_at, employee_notes")
        print("    • Настроены индексы производительности")
        print("    • Подготовлена таблица чата")
        
    except Exception as e:
        print(f"❌ Ошибка при выполнении миграции: {e}")

if __name__ == '__main__':
    fix_database()
