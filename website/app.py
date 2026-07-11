# migrate.py
import psycopg2
import os

def create_tables():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer VARCHAR(255) NOT NULL,
            phone VARCHAR(50) NOT NULL,
            address TEXT,
            product VARCHAR(255) NOT NULL,
            price DECIMAL(10,2) DEFAULT 0,
            prepaid DECIMAL(10,2) DEFAULT 0,
            priority VARCHAR(50) DEFAULT 'Обычный',
            executor VARCHAR(100) DEFAULT 'Не назначен',
            status VARCHAR(50) DEFAULT 'Новый',
            comment TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Создаем индексы для ускорения
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_executor ON orders(executor);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer);")
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Таблицы и индексы созданы успешно!")

if __name__ == '__main__':
    create_tables()
