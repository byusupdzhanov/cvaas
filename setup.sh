#!/usr/bin/env bash
set -euo pipefail

echo "Инициализация проекта CVaaS"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Ошибка: команда '$1' не найдена"
    exit 1
  fi
}

require_command docker
require_command openssl

if ! docker compose version >/dev/null 2>&1; then
  echo "Ошибка: Docker Compose v2 недоступен. Установите Docker Desktop или плагин docker compose."
  exit 1
fi

DOCKER_ACTIVITY_FILE="${HOME}/.docker/buildx/activity/desktop-linux"
if [ -e "${DOCKER_ACTIVITY_FILE}" ] && [ ! -r "${DOCKER_ACTIVITY_FILE}" ]; then
  echo "Ошибка: Docker не может прочитать ${DOCKER_ACTIVITY_FILE}"
  echo "Похоже, файл принадлежит root или другому пользователю."
  echo "Исправьте владельца вручную, например:"
  echo "  sudo chown -R \"$USER\":staff \"$HOME/.docker\""
  exit 1
fi

generate_session_secret() {
  openssl rand -hex 64
}

upsert_env_var() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env 2>/dev/null; then
    python3 - "$key" "$value" <<'PY'
from pathlib import Path
import sys

key = sys.argv[1]
value = sys.argv[2]
path = Path(".env")
lines = path.read_text().splitlines()
updated = []

for line in lines:
    if line.startswith(f"{key}="):
        updated.append(f"{key}={value}")
    else:
        updated.append(line)

path.write_text("\n".join(updated) + "\n")
PY
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

ask_https_mode() {
  local current_value="${1:-}"
  local prompt_suffix="n"

  if [ "${current_value}" = "1" ]; then
    prompt_suffix="Y"
  fi

  read -r -p "Будет ли CVaaS работать за HTTPS через reverse proxy? [y/N]: " https_answer
  https_answer="$(printf '%s' "${https_answer:-$prompt_suffix}" | tr '[:upper:]' '[:lower:]')"

  case "$https_answer" in
    y|yes|д|да)
      echo "1"
      ;;
    *)
      echo "0"
      ;;
  esac
}

if [ ! -f .env ]; then
  read -r -p "Введите имя администратора (username): " username
  read -r -s -p "Введите пароль администратора: " password
  echo ""
  session_secret="$(generate_session_secret)"
  secure_cookies="$(ask_https_mode)"

  cat > .env <<EOF
CVAAS_ADMIN_USER=${username}
CVAAS_ADMIN_PASSWORD=${password}
CVAAS_SESSION_SECRET=${session_secret}
CVAAS_SECURE_COOKIES=${secure_cookies}
EOF
  echo "✅ Файл .env создан"
else
  echo "Файл .env уже существует, используем его"
  tmp_env="$(mktemp)"
  awk '
    /^CVAAS_ADMIN_PASSWORD=/ {
      sub(/APP_UID=.*/, "", $0)
      print
      next
    }
    /^CVAAS_SESSION_SECRET=/ { print; next }
    /^CVAAS_SECURE_COOKIES=/ { print; next }
    /^APP_UID=/ { next }
    /^APP_GID=/ { next }
    { print }
  ' .env > "${tmp_env}"
  mv "${tmp_env}" .env
  echo "✅ .env очищен от legacy APP_UID/APP_GID"
fi

if ! grep -q '^CVAAS_SESSION_SECRET=' .env; then
  upsert_env_var "CVAAS_SESSION_SECRET" "$(generate_session_secret)"
  echo "✅ Сгенерирован CVAAS_SESSION_SECRET"
fi

current_secure_cookies="$(grep '^CVAAS_SECURE_COOKIES=' .env 2>/dev/null | cut -d '=' -f2- || true)"
secure_cookies="$(ask_https_mode "${current_secure_cookies}")"
upsert_env_var "CVAAS_SECURE_COOKIES" "${secure_cookies}"
echo "✅ Обновлен CVAAS_SECURE_COOKIES=${secure_cookies}"

if [ ! -f resume.db ]; then
  touch resume.db
  chmod 644 resume.db
  echo "✅ Создан пустой файл resume.db"
else
  echo "✅ resume.db уже существует"
fi

mkdir -p static/uploads/certificates
chmod -R u+rwX,go+rX static/uploads
echo "✅ Подготовлена папка static/uploads"

echo "Сборка контейнеров..."
docker compose build --no-cache

echo "Запуск..."
docker compose up -d

echo "✅ CVaaS запущен в фоне"
echo "Открыть сервис: http://localhost:8000"
echo "Посмотреть логи: docker compose logs -f"
echo "Остановить сервис: docker compose down"
