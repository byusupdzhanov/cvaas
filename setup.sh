#!/bin/bash


echo "Инициализация проекта CVaaS"

if [ ! -f .env ]; then
  read -p "Введите имя администратора (username): " username
  read -s -p "Введите пароль администратора: " password
  echo ""

  echo "CVAAS_ADMIN_USER=$username" > .env
  echo "CVAAS_ADMIN_PASSWORD=$password" >> .env
  echo "✅ Файл .env создан"
else
  echo "Файл .env уже существует, используем его"
fi

if [ ! -f resume.db ]; then
  touch resume.db
  chmod 644 resume.db
  echo "✅ Создан пустой файл resume.db"
else
  echo "✅ resume.db уже существует"
fi

mkdir -p static/uploads
chmod -R 755 static/uploads
echo "✅ Подготовлена папка static/uploads"

echo "Сборка контейнеров..."
docker-compose build --no-cache

echo "Запуск..."
docker-compose up
