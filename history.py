"""Local task storage. JSON metadata and content-addressed PDF copies; no credentials."""
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get('PAPERFIT_DATA_DIR', str(Path.home() / '.paperfit')))


@contextmanager
def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o700)
    db = sqlite3.connect(ROOT / 'history.sqlite3', timeout=15)
    db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT, updated TEXT, draft TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, task TEXT, created TEXT, status TEXT, payload TEXT)')
    (ROOT / 'history.sqlite3').chmod(0o600)
    try:
        with db:
            yield db
    finally:
        db.close()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def store_files(files):
    folder = ROOT / 'files'
    folder.mkdir(parents=True, exist_ok=True)
    saved=[]
    for name, content in files:
        digest=hashlib.sha256(content).hexdigest()
        target=folder / digest
        if not target.exists():
            target.write_bytes(content)
            target.chmod(0o600)
        saved.append({'name':name,'digest':digest})
    return saved


def read_files(refs):
    files=[]
    for ref in refs:
        digest=ref['digest']
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid stored file reference')
        files.append((ref['name'], (ROOT / 'files' / digest).read_bytes()))
    return files


def save_task(task_id, draft):
    task_id=task_id or str(uuid.uuid4())
    # Explicit whitelist: session/API settings never enter task history.
    data={k:draft.get(k) for k in ('question','source','conditions','files')}
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?,?)',
                   (task_id, draft.get('question') or '未命名任务',now(),json.dumps(data,ensure_ascii=False)))
    return task_id


def list_tasks():
    with connect() as db:
        return db.execute('SELECT id,title,updated FROM tasks ORDER BY updated DESC').fetchall()


def get_task(task_id):
    with connect() as db:
        row=db.execute('SELECT draft FROM tasks WHERE id=?',(task_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_run(task_id, report, status, run_id=None):
    run_id=run_id or str(uuid.uuid4())
    data={k:report.get(k) for k in ('question','criteria','conditions','files','source','results','searches','candidates','events','parent_run')}
    with connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload',
                   (run_id,task_id,now(),status,json.dumps(data,ensure_ascii=False)))
        db.execute('UPDATE tasks SET updated=? WHERE id=?',(now(),task_id))
    return run_id


def list_runs(task_id):
    with connect() as db:
        return db.execute('SELECT id,created,status FROM runs WHERE task=? ORDER BY created DESC,rowid DESC',(task_id,)).fetchall()


def get_run(run_id):
    with connect() as db:
        row=db.execute('SELECT payload,status FROM runs WHERE id=?',(run_id,)).fetchone()
    return (json.loads(row[0]),row[1]) if row else (None,None)


def delete_task(task_id):
    with connect() as db:
        db.execute('DELETE FROM runs WHERE task=?',(task_id,))
        db.execute('DELETE FROM tasks WHERE id=?',(task_id,))
    # Shared PDF copies are retained if any other task or version references them.
    with connect() as db:
        payloads=[r[0] for r in db.execute('SELECT draft FROM tasks')]+[r[0] for r in db.execute('SELECT payload FROM runs')]
    used={f['digest'] for p in payloads for f in (json.loads(p).get('files') or [])}
    for path in (ROOT/'files').glob('*'):
        if path.name not in used:
            path.unlink()
