import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def fix_database():
    """Исправление структуры базы данных"""
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        
        print("🔄 Исправляем структуру БД...")
        
        # 1. Добавляем колонку shop_id
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='shop_id') THEN
                    ALTER TABLE orders ADD COLUMN shop_id VARCHAR(50) DEFAULT 'moskovskaya';
                END IF;
            END $$;
        """)
        print("✅ Добавлена колонка shop_id")
        
        # 2. Обновляем существующие записи
        cur.execute("UPDATE orders SET shop_id = 'moskovskaya' WHERE shop_id IS NULL;")
        print("✅ Обновлены существующие записи")
        
        # 3. Добавляем is_archived
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='is_archived') THEN
                    ALTER TABLE orders ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        """)
        print("✅ Добавлена колонка is_archived")
        
        # 4. Добавляем completed_at
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='completed_at') THEN
                    ALTER TABLE orders ADD COLUMN completed_at TIMESTAMP;
                END IF;
            END $$;
        """)
        print("✅ Добавлена колонка completed_at")
        
        # 5. Добавляем employee_notes
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='employee_notes') THEN
                    ALTER TABLE orders ADD COLUMN employee_notes TEXT;
                END IF;
            END $$;
        """)
        print("✅ Добавлена колонка employee_notes")
        
        # 6. Создаем индексы
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_shop_id ON orders(shop_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_is_archived ON orders(is_archived);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_completed_at ON orders(completed_at);")
        print("✅ Созданы индексы")
        
        # 7. Создаем таблицу чата
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                user_name VARCHAR(100) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✅ Создана таблица chat_messages")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("🎉 База данных успешно исправлена!")
        print("   - Добавлены все необходимые колонки")
        print("   - Созданы индексы")
        print("   - Создана таблица чата")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == '__main__':
    fix_database()
