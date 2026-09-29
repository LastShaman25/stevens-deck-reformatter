"""Explicit, one-time account migration. Read-only SQLite input; empty PG target only.

Run before starting the deployment; set DATABASE_URL/STEVENS_STORAGE_NAMESPACE.
No presentations, active jobs, login sessions or cookie secrets are migrated.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.cloud import db


def migrate(path):
    source=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        with db.connect() as con:
            con.execute('SELECT pg_advisory_xact_lock(hashtext(current_schema() || \':accounts\'))')
            if con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise ValueError('Target already contains users; refusing to overwrite accounts.')
            for table,columns in [('users','id,email,issuer,subject,role,active'),
                                  ('codes','token,user_id'),('invites','token,email,role,expires')]:
                for row in source.execute(f'SELECT {columns} FROM {table}'):
                    con.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join(["%s"]*len(row))})',row)
            if source.execute("SELECT 1 FROM settings WHERE key='codes_bootstrapped'").fetchone():
                con.execute("INSERT INTO settings VALUES ('codes_bootstrapped','1') ON CONFLICT DO NOTHING")
    finally:source.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_file',type=Path)
    args=parser.parse_args()
    migrate(args.sqlite_file)
    print('Accounts migrated. Users must sign in again; local jobs remain local.')
