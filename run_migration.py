import os
import subprocess
import sys

# Задаём URL прямо в Python - минуем проблему с кодировкой Windows
DATABASE_URL = "postgresql://postgres:ymCTYuoHanxBUnnlkaZRTJHzEZGyTpSH@switchyard.proxy.rlwy.net:36316/railway"

os.environ["DATABASE_URL"] = DATABASE_URL

# Запускаем alembic
result = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    env=os.environ,
    cwd=os.path.dirname(os.path.abspath(__file__))
)
print(f"\nAlembic exit code: {result.returncode}")