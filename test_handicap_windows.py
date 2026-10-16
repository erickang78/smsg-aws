import sqlite3,unittest
import app

class HandicapWindows(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON')
  self.db.executescript('''CREATE TABLE members(id TEXT PRIMARY KEY,name TEXT,handicap REAL,note TEXT,active INTEGER);
  CREATE TABLE settings(id TEXT PRIMARY KEY,value TEXT);
  CREATE TABLE historical_scores(member_id TEXT,position INTEGER,score REAL);
  CREATE TABLE games(id TEXT PRIMARY KEY,date TEXT,course TEXT,fairway INTEGER,green INTEGER);
  CREATE TABLE game_participants(game_id TEXT,member_id TEXT,PRIMARY KEY(game_id,member_id));
  CREATE TABLE game_results(game_id TEXT,member_id TEXT,score REAL,PRIMARY KEY(game_id,member_id));''')
  self.db.executemany('INSERT INTO members VALUES(?,?,?,?,1)',[('recent','Recent',99,'',),('fallback','Fallback',99,''),('initial','Initial',7,'',)])
  self.db.execute("INSERT INTO settings VALUES('handicap_initial:initial','7')")
  self._score('recent','2026-02-01',100)
  self._score('recent','2026-08-01',4)
  self._score('recent','2026-10-01',8)
  self._score('fallback','2025-09-01',100)
  self._score('fallback','2025-12-01',14)
  self._score('fallback','2026-05-01',10)

 def _score(self,member_id,date,score):
  game_id=f'{member_id}-{date}';self.db.execute('INSERT INTO games VALUES(?,?,?,?,?)',(game_id,date,'Test',4,4));self.db.execute('INSERT INTO game_participants VALUES(?,?)',(game_id,member_id));self.db.execute('INSERT INTO game_results VALUES(?,?,?)',(game_id,member_id,score))

 def test_uses_three_month_average_when_available_and_one_year_otherwise(self):
  recent=app.recalculate_handicap(self.db,'recent','2026-10-16')
  fallback=app.recalculate_handicap(self.db,'fallback','2026-10-16')
  initial=app.recalculate_handicap(self.db,'initial','2026-10-16')
  self.assertEqual((recent['handicap'],recent['basis'],recent['window_count']),(6.0,'3M',2))
  self.assertEqual((fallback['handicap'],fallback['basis'],fallback['window_count']),(12.0,'1Y',2))
  self.assertEqual((initial['handicap'],initial['basis']), (7.0,'초기'))

if __name__=='__main__':unittest.main()
