import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate_database():
    """Обновление структуры базы данных"""
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        
        print("🔄 Начинаем миграцию базы данных...")
        
        # 1. Добавляем поле для завершения заказа
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='completed_at') THEN
                    ALTER TABLE orders ADD COLUMN completed_at TIMESTAMP;
                END IF;
            END $$;
        """)
        print("✅ Добавлено поле completed_at")
        
        # 2. Добавляем заметки сотрудника
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='employee_notes') THEN
                    ALTER TABLE orders ADD COLUMN employee_notes TEXT;
                END IF;
            END $$;
        """)
        print("✅ Добавлено поле employee_notes")
        
        # 3. Создаем таблицу чата
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
        print("✅ Создана таблица chat_messages")
        
        # 4. Создаем индексы
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_completed_at ON orders(completed_at);")
        print("✅ Созданы индексы")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("🎉 Миграция завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

if __name__ == '__main__':
    migrate_database()
