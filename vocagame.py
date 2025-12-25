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
    # DB 파일이 없는 경우를 대비한 체크
    if not os.path.exists(DB_NAME):
        # 임시로 빈 파일을 만들거나 에러를 띄울 수 있음
        pass
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    """앱 시작 시 1회만 실행될 초기화 로직"""
    conn = get_connection()
    cursor = conn.cursor()
    # 단어 테이블은 이미 있다고 가정 (사용자 코드 기준)
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
    
    # 컬럼 체크 및 추가 (하위 호환성)
    cursor.execute("PRAGMA table_info(rankings)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'total_questions' not in columns:
        try:
            cursor.execute("ALTER TABLE rankings ADD COLUMN total_questions INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.commit()

def pick_random_meaning(text):
    if not text: return ""
    parts = [p.strip() for p in text.split(';') if p.strip()]
    return random.choice(parts) if parts else text

# --- 데이터 헬퍼 함수 ---
def get_books():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT book_name FROM words")
        return [row[0] for row in cursor.fetchall() if row[0]]
    except Exception as e:
        st.error(f"DB 오류 (책 목록): {e}")
        return []

def get_chapters(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chapter FROM words WHERE book_name = ? AND chapter != 0", (book_name,))
    raw = cursor.fetchall()
    chapters = []
    for row in raw:
        try: chapters.append(int(row[0]))
        except: continue
    return sorted(list(set(chapters)))

def get_types(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT type FROM words WHERE book_name = ?", (book_name,))
    return sorted([row[0] for row in cursor.fetchall() if row[0]])

def get_words_by_range(book_name, start_chap, end_chap, selected_types=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT english, korean, type, chapter FROM words WHERE book_name = ? AND chapter >= ? AND chapter <= ?"
    params = [book_name, start_chap, end_chap]
    if selected_types:
        placeholders = ','.join(['?'] * len(selected_types))
        query += f" AND type IN ({placeholders})"
        params.extend(selected_types)
    cursor.execute(query, params)
    raw = cursor.fetchall()
    return [(eng, pick_random_meaning(kor), w_type, chap) for eng, kor, w_type, chap in raw]

def get_rankings(book, chapter, total_q):
    conn = get_connection()
    return pd.read_sql_query("""
        SELECT 
            RANK() OVER (ORDER BY score DESC, time_taken ASC) as '순위',
            player_name as '이름', 
            (score || ' / ' || total_questions) as '점수',
            round(time_taken, 2) as '시간(초)', 
            datetime(played_at, 'localtime') as '날짜'
        FROM rankings 
        WHERE book_name = ? AND chapter = ? AND total_questions = ?
        ORDER BY score DESC, time_taken ASC 
    """, conn, params=(book, chapter, total_q))

def save_score(name, book, chapter, score, total_q, time_taken):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO rankings (player_name, book_name, chapter, score, total_questions, time_taken)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, book, int(chapter), int(score), int(total_q), float(time_taken)))
    conn.commit()

# --- 앱 UI 및 로직 ---
st.set_page_config(page_title="쑥쑥단어게임", page_icon="⚡", layout="wide")
init_db()

# 세션 상태 초기화
if 'stage' not in st.session_state: st.session_state['stage'] = 'setup'
if 'score' not in st.session_state: st.session_state['score'] = 0

# 콜백 함수 정의 (게임 진행용)
def handle_answer_click(selected_meaning, current_idx):
    # 중복 클릭 방지
    if current_idx in st.session_state.get('solved_indexes', set()):
        return

    correct_meaning = st.session_state['words'][current_idx][1]
    
    if selected_meaning == correct_meaning:
        st.session_state['score'] += 1
        st.toast("⭕ 정답입니다!", icon="✅")
    else:
        st.toast(f"❌ 틀렸습니다! 정답: {correct_meaning}", icon="⚠️")
    
    st.session_state['solved_indexes'].add(current_idx)
    
    # 다음 문제 또는 종료
    if st.session_state['current_q'] + 1 < st.session_state['total_q']:
        st.session_state['current_q'] += 1
    else:
        st.session_state['end_time'] = time.time()
        st.session_state['stage'] = 'finished'

# --- 화면 렌더링 ---

# 사이드바 (챔피언 정보)
with st.sidebar:
    st.title("🏆 명예의 전당")
    books = get_books()
    for b in books:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT player_name, score, total_questions FROM rankings WHERE book_name = ? AND chapter = 0 ORDER BY score DESC, time_taken ASC LIMIT 1", (b,))
        res = cursor.fetchone()
        if res:
            st.info(f"**{b}**\n👑 {res[0]} ({res[1]}/{res[2]})")

# 1. 설정 단계
if st.session_state['stage'] == 'setup':
    st.title("⚡ 쑥쑥단어게임 설정")
    books = get_books()
    if not books:
        st.warning("DB에 등록된 단어장이 없습니다. DB 파일을 확인해주세요.")
    else:
        selected_book = st.selectbox("📘 단어장 선택", books)
        chapters = get_chapters(selected_book)
        
        col1, col2 = st.columns(2)
        with col1: start_ch = st.selectbox("시작 챕터", chapters, index=0)
        with col2: end_ch = st.selectbox("종료 챕터", chapters, index=len(chapters)-1)
        
        types = get_types(selected_book)
        sel_types = st.multiselect("유형 선택 (비우면 전체)", types, default=types)
        
        q_count_opt = st.radio("문제 수", ["10", "20", "40", "전체"], horizontal=True, index=1)
        
        if st.button("🚀 게임 시작!", type="primary", use_container_width=True):
            words = get_words_by_range(selected_book, start_ch, end_ch, sel_types)
            if not words:
                st.error("해당 범위에 단어가 없습니다!")
            else:
                if q_count_opt == "전체": target_n = len(words)
                else: target_n = min(len(words), int(q_count_opt))
                
                final_words = random.sample(words, target_n)
                st.session_state.update({
                    'words': final_words,
                    'total_q': target_n,
                    'current_q': 0,
                    'score': 0,
                    'start_time': time.time(),
                    'stage': 'playing',
                    'solved_indexes': set(),
                    'book': selected_book,
                    'chapter': 0 if (start_ch == min(chapters) and end_ch == max(chapters)) else (start_ch if start_ch == end_ch else -1)
                })
                # 이전 게임 옵션 초기화
                for k in list(st.session_state.keys()):
                    if k.startswith('opts_'): del st.session_state[k]
                st.rerun()

# 2. 게임 진행 단계
elif st.session_state['stage'] == 'playing':
    idx = st.session_state['current_q']
    words = st.session_state['words']
    curr_word = words[idx]
    
    # 진행도 표시
    st.progress((idx) / st.session_state['total_q'], text=f"문제 {idx+1} / {st.session_state['total_q']}")
    
    st.markdown(f"<h1 style='text-align: center; font-size: 60px;'>{curr_word[0]}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: gray;'>({curr_word[2]} / Ch.{curr_word[3]})</p>", unsafe_allow_html=True)
    
    # 보기 생성 (세션에 저장하여 고정)
    opt_key = f'opts_{idx}'
    if opt_key not in st.session_state:
        correct = curr_word[1]
        # 오답 후보들 (현재 범위 내 단어들의 모든 뜻 중 정답 제외)
        all_meanings = list(set([w[1] for w in words if w[1] != correct]))
        if len(all_meanings) < 3:
            wrong_opts = all_meanings + ["(오답 부족)"] * (3 - len(all_meanings))
        else:
            wrong_opts = random.sample(all_meanings, 3)
        
        options = wrong_opts + [correct]
        random.shuffle(options)
        st.session_state[opt_key] = options
    
    options = st.session_state[opt_key]
    
    # 버튼 레이아웃
    col1, col2 = st.columns(2)
    for i, opt in enumerate(options):
        with (col1 if i < 2 else col2):
            st.button(f"{i+1}. {opt}", use_container_width=True, key=f"btn_{idx}_{i}", 
                      on_click=handle_answer_click, args=(opt, idx))

# 3. 게임 종료 단계
elif st.session_state['stage'] == 'finished':
    st.balloons()
    total_time = st.session_state['end_time'] - st.session_state['start_time']
    score = st.session_state['score']
    total = st.session_state['total_q']
    
    st.markdown(f"<h2 style='text-align: center;'>🎉 수고하셨습니다!</h2>", unsafe_allow_html=True)
    st.metric("최종 점수", f"{score} / {total}", f"{int(score/total*100)}%")
    st.write(f"소요 시간: {total_time:.2f}초")
    
    with st.form("ranking_save"):
        name = st.text_input("닉네임을 입력하세요", placeholder="홍길동")
        if st.form_submit_button("랭킹 등록"):
            if name:
                save_score(name, st.session_state['book'], st.session_state['chapter'], score, total, total_time)
                st.session_state['stage'] = 'ranking'
                st.rerun()
            else:
                st.warning("이름을 입력해야 저장할 수 있습니다.")
    
    if st.button("처음으로"):
        st.session_state['stage'] = 'setup'
        st.rerun()

# 4. 랭킹 확인 단계
elif st.session_state['stage'] == 'ranking':
    st.title("📊 명예의 전당")
    book = st.session_state['book']
    chap = st.session_state['chapter']
    
    df = get_rankings(book, chap, st.session_state['total_q'])
    if df.empty:
        st.info("아직 이 조건의 랭킹 데이터가 없습니다.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        
    if st.button("새 게임 시작"):
        st.session_state['stage'] = 'setup'
        st.rerun()
