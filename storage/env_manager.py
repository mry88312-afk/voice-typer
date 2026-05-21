"""安全讀寫 .env (只更新指定 key，保留註解)"""
import os
import re
from pathlib import Path


class EnvManager:
    def __init__(self, env_path: Path):
        self.path = env_path

    def read(self) -> dict:
        result = {}
        if not self.path.exists():
            return result
        with open(self.path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', line)
                if m:
                    key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
                    result[key] = value
        return result

    def get(self, key: str) -> str | None:
        return self.read().get(key)

    def set(self, key: str, value: str):
        """寫入或更新 key，保留檔案中既有的註解與順序"""
        lines = []
        found = False

        if self.path.exists():
            with open(self.path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        lines.append(line)
                        continue
                    m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', stripped)
                    if m and m.group(1) == key:
                        lines.append(f'{key}={value}\n')
                        found = True
                    else:
                        lines.append(line)

        if not found:
            if lines and not lines[-1].endswith('\n'):
                lines.append('\n')
            lines.append(f'{key}={value}\n')

        with open(self.path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        # 立即更新當前 process 的環境變數
        os.environ[key] = value

    def is_valid(self, key: str, prefix: str = '') -> bool:
        """檢查 key 存在且非預設樣板值"""
        v = self.get(key)
        if not v:
            return False
        if 'your-' in v.lower():
            return False
        if prefix and not v.startswith(prefix):
            return False
        return True
