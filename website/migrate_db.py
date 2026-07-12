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
        
        # 3. Добавляем поле created_by (кто создал заказ)
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='created_by') THEN
                    ALTER TABLE orders ADD COLUMN created_by VARCHAR(255);
                END IF;
            END $$;
        """)
        print("✅ Добавлено поле created_by")
        
        # 4. Добавляем поле executor_id (ID исполнителя)
        cur.execute("""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='orders' AND column_name='executor_id') THEN
                    ALTER TABLE orders ADD COLUMN executor_id VARCHAR(255);
                END IF;
            END $$;
        """)
        print("✅ Добавлено поле executor_id")
        
        # 5. Создаем таблицу чата
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
        
        # 6. Создаем индексы для оптимизации
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_completed_at ON orders(completed_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_by ON orders(created_by);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_executor_id ON orders(executor_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_executor_status ON orders(executor, status);")
        print("✅ Созданы индексы")
        
        # 7. Обновляем существующие заказы (если есть исполнитель, но нет created_by)
        cur.execute("""
            UPDATE orders 
            SET created_by = executor 
            WHERE created_by IS NULL AND executor IS NOT NULL AND executor != 'Не назначен';
        """)
        print("✅ Обновлены существующие заказы")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("🎉 Миграция завершена успешно!")
        print("\n📋 Добавленные поля:")
        print("  - completed_at (TIMESTAMP) - дата завершения заказа")
        print("  - employee_notes (TEXT) - заметки сотрудника")
        print("  - created_by (VARCHAR) - кто создал заказ")
        print("  - executor_id (VARCHAR) - ID исполнителя")
        print("\n📋 Созданные таблицы:")
        print("  - chat_messages - сообщения чата")
        print("\n📋 Созданные индексы:")
        print("  - idx_chat_messages_created_at")
        print("  - idx_orders_completed_at")
        print("  - idx_orders_created_by")
        print("  - idx_orders_executor_id")
        print("  - idx_orders_executor_status")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        print("\n🔍 Проверьте:")
        print("  1. Правильность DATABASE_URL в .env файле")
        print("  2. Доступность базы данных")
        print("  3. Права на изменение структуры таблиц")

def check_database_structure():
    """Проверка текущей структуры базы данных"""
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cur = conn.cursor()
        
        print("\n📊 Текущая структура таблицы orders:")
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'orders'
            ORDER BY ordinal_position;
        """)
        columns = cur.fetchall()
        for col in columns:
            print(f"  - {col[0]}: {col[1]} (nullable: {col[2]})")
        
        print("\n📊 Существующие таблицы:")
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cur.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")

if __name__ == '__main__':
    print("=" * 50)
    print("🛠️  УТИЛИТА МИГРАЦИИ БАЗЫ ДАННЫХ")
    print("=" * 50)
    
    # Показываем текущую структуру
    check_database_structure()
    
    # Запускаем миграцию
    print("\n" + "=" * 50)
    migrate_database()
    
    # Показываем обновленную структуру
    print("\n" + "=" * 50)
    check_database_structure()
    
    print("\n✅ Готово! База данных обновлена.")
