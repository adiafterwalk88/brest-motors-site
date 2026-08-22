# CRM Заказы

Простая CRM система для управления заказами с подключением к Supabase.

## Возможности

- 🔐 Авторизация и регистрация пользователей
- 📦 Создание, просмотр, редактирование и удаление заказов
- 🔍 Поиск по номеру заказа и имени клиента
- 🏷️ Фильтрация по статусу
- 📄 Пагинация
- 🎨 Адаптивный дизайн

## Технологии

- HTML / CSS / JavaScript (Vanilla)
- Supabase (аутентификация + база данных)
- Font Awesome (иконки)

## Настройка

### 1. Создайте проект в Supabase

1. Зарегистрируйтесь на [supabase.com](https://supabase.com)
2. Создайте новый проект
3. В редакторе SQL выполните следующий код для создания таблицы:

```sql
CREATE TABLE orders (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL,
    client_name TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'новый',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_order_number ON orders(order_number);
