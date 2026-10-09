"""Normalize known customer countries with an audit trail; unknown values stay intact."""
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from country_names import normalize_country

if __name__ == '__main__':
    conn = sqlite3.connect(sys.argv[1])
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        changed = 0
        for customer_id, old in conn.execute('SELECT id, country FROM customers').fetchall():
            new = normalize_country(old)
            if not old or old == new:
                continue
            conn.execute('UPDATE customers SET country=?, version=coalesce(version, 1)+1 WHERE id=?', (new, customer_id))
            conn.execute("INSERT INTO audit_logs (username,action,entity_type,entity_id,summary,before_json,after_json,ip_address,created_at) VALUES ('system','update','customer',?,'统一客户国家名称',?,?, '',datetime('now'))", (customer_id, json.dumps({'country':old},ensure_ascii=False), json.dumps({'country':new},ensure_ascii=False)))
            changed += 1
    print('Countries normalized:', changed)
    conn.close()
