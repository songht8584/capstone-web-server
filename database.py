import sqlite3
import os
from flask import g

DATABASE_PATH = 'greeneye.db'

def get_db():
    """DB 연결 객체 반환"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception):
    """DB 연결 종료"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """DB 테이블 초기 생성"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                points INTEGER DEFAULT 0
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                org_filename TEXT NOT NULL,
                res_filename TEXT NOT NULL,
                score INTEGER,
                result_status TEXT,
                details_json TEXT,
                image_hash TEXT
            )
        ''')

def reset_db_data():
    """DB 데이터 비우기 (로그인 시 호출)"""
    # Flask 앱 컨텍스트 안에서 호출될 때는 get_db() 사용 가능
    # 여기서는 독립적인 연결로 처리하여 안정성 확보
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute('DELETE FROM history')
        # user 테이블은 유지 (로그인 정보 유지 위해)

def get_history_count(username):
    """특정 사용자의 전체 기록 개수 반환"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.execute('SELECT COUNT(*) FROM history WHERE username = ?', (username,))
        return cursor.fetchone()[0]

def get_history_paginated(username, page, per_page):
    """특정 페이지의 데이터만 가져오기 (LIMIT, OFFSET 사용)"""
    offset = (page - 1) * per_page
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM history 
            WHERE username = ? 
            ORDER BY id DESC 
            LIMIT ? OFFSET ?
        ''', (username, per_page, offset))
        return cursor.fetchall()