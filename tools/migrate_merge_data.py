"""一次性資料合併：專案根目錄 → %APPDATA%/VoiceTyper。跑一次即可。
策略：APPDATA 為主（最新）；只補「APPDATA 缺少」的 .env key 與 profile 詞彙。
history/usage/learned 不自動合併（風險高、價值低），原檔搬進 legacy_backup/ 保留。"""
import json, os, re, shutil, time
from pathlib import Path

PROJECT = Path(r'C:\Users\mry88\voice-typer')
APPDATA = Path(os.environ['APPDATA']) / 'VoiceTyper'
BACKUP = APPDATA / ('backup-' + time.strftime('%Y%m%d-%H%M%S'))
LEGACY = PROJECT / 'legacy_backup'
DATA_FILES = ['.env', 'config.json', 'history.json', 'usage.json',
              'learned_words.json', 'voice-typer.log']

def read_env(p: Path) -> dict:
    d = {}
    if not p.exists():
        return d
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', line)
        if m:
            d[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return d

def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default

def main():
    assert APPDATA.exists(), 'APPDATA/VoiceTyper 不存在，中止（不該發生）'
    # 1. 備份 APPDATA 現況
    BACKUP.mkdir(parents=True)
    for name in DATA_FILES:
        src = APPDATA / name
        if src.exists():
            shutil.copy(str(src), str(BACKUP / name))
    print(f'[1/4] 已備份 APPDATA -> {BACKUP}')

    # 2. .env：補上專案有、APPDATA 沒有的 key（不覆蓋既有值）
    proj_env, app_env = read_env(PROJECT / '.env'), read_env(APPDATA / '.env')
    added = [k for k, v in proj_env.items()
             if k not in app_env and v and 'your-' not in v.lower()]
    if added:
        with open(APPDATA / '.env', 'a', encoding='utf-8') as f:
            f.write('\n# merged from project dir ' + time.strftime('%Y-%m-%d') + '\n')
            for k in added:
                f.write(f'{k}={proj_env[k]}\n')
    print(f'[2/4] .env 合併，新增 key: {added if added else "無"}')

    # 3. config：APPDATA 為主，各 profile 詞彙取聯集；舊版頂層 vocabulary 併入 default
    pc = load_json(PROJECT / 'config.json', {})
    ac = load_json(APPDATA / 'config.json', {})
    ap = {p.get('id'): p for p in ac.get('profiles', [])}
    merged = {}
    for prof in pc.get('profiles', []):
        pid = prof.get('id')
        if pid in ap:
            old = list(ap[pid].get('vocabulary') or [])
            add = [w for w in (prof.get('vocabulary') or []) if w and w not in old]
            if add:
                ap[pid]['vocabulary'] = old + add
                merged[pid] = add
    top_vocab = [w for w in (pc.get('vocabulary') or []) if w]
    if top_vocab and 'default' in ap:
        old = list(ap['default'].get('vocabulary') or [])
        add = [w for w in top_vocab if w not in old]
        if add:
            ap['default']['vocabulary'] = old + add
            merged.setdefault('default', [])
            merged['default'] += add
    if merged:
        ac['profiles'] = list(ap.values())
        (APPDATA / 'config.json').write_text(
            json.dumps(ac, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[3/4] 詞彙合併: {merged if merged else "無新增"}')

    # 4. 專案根目錄舊資料檔搬進 legacy_backup/（保留可救回，避免日後混淆）
    LEGACY.mkdir(exist_ok=True)
    moved = []
    for name in DATA_FILES + ['recordings']:
        src = PROJECT / name
        if src.exists():
            shutil.move(str(src), str(LEGACY / name))
            moved.append(name)
    print(f'[4/4] 已搬移專案舊資料 -> legacy_backup/: {moved}')
    print('完成。')

if __name__ == '__main__':
    main()
