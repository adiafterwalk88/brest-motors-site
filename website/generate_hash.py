#!/usr/bin/env python3
"""
Генератор хешей паролей для CRM
Запуск: python generate_hash.py
"""

import getpass
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def main():
    print("\n🔑 ГЕНЕРАТОР ХЕШЕЙ ПАРОЛЕЙ ДЛЯ .ENV")
    print("=" * 50)
    
    hashes_to_save = []
    
    # Администратор
    print("\n👤 АДМИНИСТРАТОР:")
    admin_pwd = getpass.getpass("  Введите пароль админа (символы скрыты): ").strip()
    if admin_pwd:
        h = hash_password(admin_pwd)
        hashes_to_save.append(f"ADMIN_PASSWORD_HASH='{h}'")
        print("  ✅ Хеш сгенерирован")
    
    # Сотрудники
    employees = [
        ('pavel_ivanovich', 'Павел Иванович'),
        ('pavel', 'Павел'),
        ('dmitry', 'Дмитрий'),
        ('alexander', 'Александр')
    ]
    
    print("\n👨‍🔧 СОТРУДНИКИ (нажмите Enter, чтобы пропустить):")
    for emp_id, emp_name in employees:
        pwd = getpass.getpass(f"  {emp_name}: ").strip()
        if pwd:
            h = hash_password(pwd)
            hashes_to_save.append(f"PASSWORD_HASH_{emp_id.upper()}='{h}'")
            print(f"  ✅ Хеш для {emp_name} сгенерирован")

    print("\n" + "=" * 50)
    print("📋 СКОПИРУЙТЕ И ВСТАВЬТЕ ЭТИ СТРОКИ В ФАЙЛ .env:\n")
    for line in hashes_to_save:
        print(line)
    print("\n" + "=" * 50)

if __name__ == '__main__':
    main()
