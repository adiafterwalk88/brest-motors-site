#!/usr/bin/env python3
"""
Генератор хешей паролей для CRM
Запуск: python generate_hash.py
"""

import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def main():
    print("\n🔑 ГЕНЕРАТОР ХЕШЕЙ ПАРОЛЕЙ")
    print("=" * 50)
    
    # Администратор
    print("\n👤 АДМИНИСТРАТОР:")
    admin_pwd = input("  Пароль: ").strip()
    if admin_pwd:
        print(f"  ADMIN_PASSWORD_HASH={hash_password(admin_pwd)}")
    
    # Сотрудники
    employees = [
        ('pavel_ivanovich', 'Павел Иванович'),
        ('pavel', 'Павел'),
        ('dmitry', 'Дмитрий'),
        ('alexander', 'Александр')
    ]
    
    print("\n👨‍🔧 СОТРУДНИКИ:")
    for emp_id, emp_name in employees:
        pwd = input(f"  {emp_name}: ").strip()
        if pwd:
            print(f"  PASSWORD_HASH_{emp_id.upper()}={hash_password(pwd)}")
    
    print("\n" + "=" * 50)
    print("✅ Скопируйте эти строки в файл .env")
    print("   Пример: ADMIN_PASSWORD_HASH=$2b$12$...")
    print("   Удалите старые пароли из кода!")

if __name__ == '__main__':
    main()
