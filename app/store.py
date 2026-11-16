import os,sqlite3,json,time
from pathlib import Path
from app.errors import RuleError
def connect():
    path=os.environ.get('DB_PATH','/tmp/coldchain.sqlite3')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=15);con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, reviewed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS owner_reviews(run_id TEXT NOT NULL, owner TEXT NOT NULL, version INTEGER NOT NULL, created TEXT NOT NULL, PRIMARY KEY(run_id,owner))')
    return con

def save(bundle):
    rid=bundle['manifest']['run_id']
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO runs(id,payload,created) VALUES(?,?,?)',(rid,json.dumps(bundle,ensure_ascii=False),bundle['manifest']['created_at']))
        row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed'])
    return out

def get(rid):
    with connect() as c: row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    if not row:return None
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed']);return out

def latest():
    with connect() as c: row=c.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    if not row:return None
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed']);return out

def history():
    with connect() as c: rows=c.execute('SELECT id,version,reviewed,created FROM runs ORDER BY rowid DESC').fetchall()
    return [dict(r) for r in rows]

def reviews_for(rid):
    with connect() as c: rows=c.execute('SELECT owner FROM owner_reviews WHERE run_id=? ORDER BY owner',(rid,)).fetchall()
    return [r['owner'] for r in rows]

def review(rid,version,owners,complete):
    now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    with connect() as c:
        row=c.execute('SELECT version FROM runs WHERE id=?',(rid,)).fetchone()
        if not row:raise RuleError('NOT_FOUND','批次不存在或不是当前批次',404)
        if row['version']!=version:raise RuleError('STALE','记录已变更，请刷新后复核',409)
        for owner in owners:
            c.execute('INSERT OR IGNORE INTO owner_reviews(run_id,owner,version,created) VALUES(?,?,?,?)',(rid,owner,version,now))
        c.execute('UPDATE runs SET version=version+1,reviewed=? WHERE id=? AND version=?',(1 if complete else 0,rid,version))
    return {'run_id':rid,'version':version+1,'reviewed':complete}
