#!/bin/bash

# Скрипт установки и запуска анализатора коммерческих предложений

set -e

echo "========================================="
echo "Анализатор коммерческих предложений"
echo "========================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не установлен. Установите Python 3.12 или выше."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION обнаружен"

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
    echo "✅ Виртуальное окружение создано"
fi

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate

# Установка зависимостей
echo "Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Зависимости установлены"

# Создание тестовых данных
if [ ! -f "data/test_proposals.xlsx" ]; then
    echo "Создание тестовых данных..."
    python utils/create_test_data.py
    echo "✅ Тестовые данные созданы"
fi

# Настройка окружения
if [ ! -f ".env" ]; then
    echo "Создание файла .env из примера..."
    cp .env.example .env
    echo "⚠️  Отредактируйте файл .env и добавьте ваш OpenRouter API ключ"
    echo "   OPENROUTER_API_KEY=your_api_key_here"
fi

echo ""
echo "========================================="
echo "Установка завершена!"
echo "========================================="
echo ""
echo "Для запуска приложения выполните:"
echo "1. source venv/bin/activate"
echo "2. streamlit run main.py"
echo ""
echo "Приложение будет доступно по адресу: http://localhost:8501"
echo ""
echo "Для тестирования без API ключа используйте простой анализ"
echo "или получите ключ на https://openrouter.ai/"