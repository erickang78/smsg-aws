"""Store a snapshot each time a game's grouping is saved."""
import json


def init_grouping_history(connection):
    connection.executescript("""
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS game_grouping_history (
    id INTEGER PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    saved_at TEXT,
    groups_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS game_grouping_history_game ON game_grouping_history(game_id, id);
INSERT INTO game_grouping_history(game_id, groups_json)
SELECT g.game_id, g.groups_json FROM game_groupings g
WHERE NOT EXISTS (SELECT 1 FROM game_grouping_history h WHERE h.game_id=g.game_id);
CREATE TRIGGER IF NOT EXISTS game_grouping_history_insert
AFTER INSERT ON game_groupings BEGIN
    INSERT INTO game_grouping_history(game_id, saved_at, groups_json)
    VALUES (NEW.game_id, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), NEW.groups_json);
END;
CREATE TRIGGER IF NOT EXISTS game_grouping_history_update
AFTER UPDATE OF groups_json ON game_groupings BEGIN
    INSERT INTO game_grouping_history(game_id, saved_at, groups_json)
    VALUES (NEW.game_id, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), NEW.groups_json);
END;
COMMIT;
""")


def list_grouping_history(connection, game_id):
    return [
        {"version": version, "saved_at": saved_at, "groups": json.loads(groups_json)}
        for version, (_, saved_at, groups_json) in enumerate(connection.execute(
            "SELECT id, saved_at, groups_json FROM game_grouping_history WHERE game_id=? ORDER BY id",
            (game_id,),
        ), 1)
    ][::-1]
