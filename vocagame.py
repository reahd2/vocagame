import streamlit as st
import sqlite3
import random
import time
import pandas as pd
import os

# DB 파일 이름 설정
DB_NAME = 'english_words_final.db'

# --- 데이터베이스 관리 ---
@st.cache_resource
def get_connection():
    # DB 파일 존재 여부 확인
    if not os.path.exists(DB_NAME):
        # 파일이 없으면 빈 상태로 앱이 멈추지 않게 함
        return None
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    if conn is None:
        return
    
    cursor = conn.cursor()
    # 랭킹 테이블 생성
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT,
            book_name TEXT,
            chapter INTEGER,
            score INTEGER,
            total_questions INTEGER DEFAULT 0,
            time_taken REAL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 컬럼 체크 및 추가
    cursor.execute("PRAGMA table_info(rankings)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'total_questions' not in columns:
        try:
            cursor.execute("ALTER TABLE rankings ADD COLUMN total_questions INTEGER DEFAULT 0")
        except:
            pass
    conn.commit()

# --- 데이터 헬퍼 함수 ---
def get_books():
    conn = get_connection()
    if conn is None:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT book_name FROM words")
        return [row[0] for row in cursor.fetchall() if row[0]]
    except sqlite3.OperationalError:
        # words 테이블이 없는 경우 대비
        return []

# ... (기타 get_chapters, get_types 등은 동일하게 유지하되 conn 체크 추가) ...

def get_chapters(book_name):
    conn = get_connection()
    if conn is None: return []
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chapter FROM words WHERE book_name = ? AND chapter != 0", (book_name,))
    return sorted([int(row[0]) for row in cursor.fetchall() if str(row[0]).isdigit()])

# --- 앱 UI 및 로직 ---
st.set_page_config(page_title="쑥쑥단어game", page_icon="⚡", layout="wide")
init_db()

# 세션 상태 초기화 (기존 코드 유지)
if 'stage' not in st.session_state: st.session_state['stage'] = 'setup'
if 'score' not in st.session_state: st.session_state['score'] = 0

# --- 화면 렌더링 ---

# 1. 설정 단계
if st.session_state['stage'] == 'setup':
    st.title("⚡ 쑥쑥단어게임 설정")
    
    if not os.path.exists(DB_NAME):
        st.error(f"⚠️ '{DB_NAME}' 파일을 찾을 수 없습니다. GitHub 저장소에 DB 파일을 업로드했는지 확인해주세요.")
        st.stop() # 여기서 실행 중단

    books = get_books()
    if not books:
        st.warning("DB에 'words' 테이블이 없거나 데이터가 없습니다.")
    else:
        selected_book = st.selectbox("📘 단어장 선택", books)
        chapters = get_chapters(selected_book)
        
        if not chapters:
            st.error("선택한 단어장에 챕터 정보가 없습니다.")
        else:
            col1, col2 = st.columns(2)
            with col1: start_ch = st.selectbox("시작 챕터", chapters, index=0)
            with col2: end_ch = st.selectbox("종료 챕터", chapters, index=len(chapters)-1)
            
            # ... (이하 로직 동일) ...
            if st.button("🚀 게임 시작!", type="primary", use_container_width=True):
                # 게임 시작 로직 실행
                pass
