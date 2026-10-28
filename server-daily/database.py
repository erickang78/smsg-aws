"""SQLite connection and schema initialization for SMSG."""
import json, os, sqlite3
from pathlib import Path
ROOT = Path(__file__).parent
DB = Path(os.environ.get('SMSG_DB', str(ROOT / 'data' / 'smsg.sqlite3')))

def connect():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c


def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS game_groupings(game_id TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,groups_json TEXT NOT NULL,group_count INTEGER NOT NULL,group_size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS game_notes(game_id TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY,date TEXT NOT NULL,course TEXT NOT NULL,fairway INTEGER NOT NULL,green INTEGER NOT NULL,deleted_at INTEGER);
CREATE TABLE IF NOT EXISTS game_change_log(id INTEGER PRIMARY KEY AUTOINCREMENT,game_id TEXT NOT NULL,action TEXT NOT NULL,game_date TEXT NOT NULL,course TEXT NOT NULL,changed_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS game_participants(game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,member_id TEXT NOT NULL REFERENCES members(id),PRIMARY KEY(game_id,member_id));
CREATE TABLE IF NOT EXISTS historical_scores(member_id TEXT NOT NULL REFERENCES members(id),position INTEGER NOT NULL,score REAL NOT NULL,PRIMARY KEY(member_id,position));
CREATE TABLE IF NOT EXISTS game_results(game_id TEXT NOT NULL,member_id TEXT NOT NULL,score REAL NOT NULL,PRIMARY KEY(game_id,member_id),FOREIGN KEY(game_id,member_id) REFERENCES game_participants(game_id,member_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,handicap REAL NOT NULL,note TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,phone TEXT NOT NULL DEFAULT '',nickname TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS meals(id TEXT PRIMARY KEY,date TEXT NOT NULL,place TEXT NOT NULL,people INTEGER NOT NULL,income INTEGER NOT NULL,extra INTEGER NOT NULL,expense INTEGER NOT NULL,note TEXT NOT NULL,position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rounds(date TEXT PRIMARY KEY,groups_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS member_logins(member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,username TEXT NOT NULL UNIQUE,salt TEXT NOT NULL,password_hash TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,reset INTEGER NOT NULL);''')
  if 'phone' not in [r['name'] for r in c.execute('PRAGMA table_info(members)')]:
   c.execute("ALTER TABLE members ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
  if 'nickname' not in [r['name'] for r in c.execute('PRAGMA table_info(members)')]:
   c.execute("ALTER TABLE members ADD COLUMN nickname TEXT NOT NULL DEFAULT ''")
  if 'deleted_at' not in [r['name'] for r in c.execute('PRAGMA table_info(games)')]:
   c.execute('ALTER TABLE games ADD COLUMN deleted_at INTEGER')
  if 'member_id' not in [r['name'] for r in c.execute('PRAGMA table_info(sessions)')]:
   c.execute('ALTER TABLE sessions ADD COLUMN member_id TEXT REFERENCES members(id)')
  c.execute('BEGIN IMMEDIATE')
  if not c.execute("SELECT 1 FROM settings WHERE id='seeded'").fetchone():
   for i,r in enumerate(json.loads((ROOT/'seed.json').read_text())):
    c.execute('INSERT INTO meals VALUES(?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ['id','date','place','people','income','extra','expense','note'])+(i,))
   c.execute("INSERT INTO settings VALUES('opening','132843')");c.execute("INSERT INTO settings VALUES('seeded','1')")
