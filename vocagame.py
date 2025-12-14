import streamlit as st
import sqlite3
import random
import time
import pandas as pd
import re

# DB 파일 이름 설정
DB_NAME = 'english_words_final.db'

# --- 데이터베이스 및 유틸리티 함수 ---
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def pick_random_meaning(text):
    """뜻 여러 개 중 하나 랜덤 선택 (세미콜론 기준)"""
    if not text:
        return ""
    parts = text.split(';')
    meanings = [p.strip() for p in parts if p.strip()]
    if meanings:
        return random.choice(meanings)
    return text

def create_rankings_table():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT,
            book_name TEXT,
            chapter INTEGER,
            score INTEGER,
            total_questions INTEGER,
            time_taken REAL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 컬럼 누락 확인 및 추가
    cursor.execute("PRAGMA table_info(rankings)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'total_questions' not in columns:
        try:
            cursor.execute("ALTER TABLE rankings ADD COLUMN total_questions INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
            
    conn.commit()
    conn.close()

def get_books():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT book_name FROM words")
    books = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return books

def get_chapters(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chapter FROM words WHERE book_name = ? ORDER BY chapter", (book_name,))
    chapters = [row[0] for row in cursor.fetchall()]
    conn.close()
    return chapters

def get_types(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT type FROM words WHERE book_name = ?", (book_name,))
    types = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return sorted([t for t in types if t])

def get_words(book_name, chapter, selected_types=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT english, korean, type FROM words WHERE book_name = ?"
    params = [book_name]
    
    if chapter != 0:
        query += " AND chapter = ?"
        params.append(chapter)
        
    if selected_types:
        placeholders = ','.join(['?'] * len(selected_types))
        query += f" AND type IN ({placeholders})"
        params.extend(selected_types)
        
    cursor.execute(query, params)
    raw_words = cursor.fetchall()
    conn.close()
    
    processed_words = []
    for eng, kor, w_type in raw_words:
        random_kor = pick_random_meaning(kor)
        processed_words.append((eng, random_kor, w_type))
    return processed_words

def get_book_champion(book_name):
    """
    통합 챔피언: 전체 챕터(0)에서 '절대 점수(score)'가 가장 높은 사람.
    (문제를 많이 풀어서 많이 맞힌 사람이 유리하므로 공정함)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT player_name, score, total_questions 
        FROM rankings 
        WHERE book_name = ? AND chapter = 0 
        ORDER BY score DESC, time_taken ASC 
        LIMIT 1
    """, (book_name,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_score_if_best(name, book, chapter, score, total_q, time_taken):
    """
    [수정] 같은 챕터라도 '문제 수(total_questions)'가 다르면 별개의 기록으로 저장합니다.
    예: 20문제 푼 기록 vs 40문제 푼 기록은 따로 관리됨.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 개인 기록 확인 (이름, 책, 챕터, AND 문제수)
    cursor.execute("""
        SELECT id, score, time_taken FROM rankings 
        WHERE player_name = ? AND book_name = ? AND chapter = ? AND total_questions = ?
    """, (name, book, chapter, total_q))
    row = cursor.fetchone()
    
    should_update = False
    
    if row:
        existing_id, old_score, old_time = row
        # 점수 갱신 조건
        if score > old_score or (score == old_score and time_taken < old_time):
            cursor.execute("""
                UPDATE rankings 
                SET score = ?, time_taken = ?, played_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (score, time_taken, existing_id))
            should_update = True
    else:
        cursor.execute("""
            INSERT INTO rankings (player_name, book_name, chapter, score, total_questions, time_taken)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, book, chapter, score, total_q, time_taken))
        should_update = True
    
    # 2. TOP 10 관리 (해당 챕터 & 해당 문제 수 그룹 내에서만)
    if should_update:
        cursor.execute("""
            SELECT id FROM rankings 
            WHERE book_name = ? AND chapter = ? AND total_questions = ?
            ORDER BY score DESC, time_taken ASC
            LIMIT 10
        """, (book, chapter, total_q))
        top_10_ids = [r[0] for r in cursor.fetchall()]
        
        if top_10_ids:
            placeholders = ','.join(['?'] * len(top_10_ids))
            # 해당 그룹(문제 수) 내에서 10위 밖 삭제
            cursor.execute(f"""
                DELETE FROM rankings 
                WHERE book_name = ? AND chapter = ? AND total_questions = ? AND id NOT IN ({placeholders})
            """, (book, chapter, total_q, *top_10_ids))
            
    conn.commit()
    conn.close()
    return should_update

def get_existing_question_counts(book, chapter):
    """해당 챕터의 랭킹 데이터에 존재하는 '문제 수' 종류를 가져옴 (예: [20, 30, 40])"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT total_questions FROM rankings 
        WHERE book_name = ? AND chapter = ? 
        ORDER BY total_questions DESC
    """, (book, chapter))
    counts = [row[0] for row in cursor.fetchall()]
    conn.close()
    return counts

def get_rankings(book, chapter, total_q):
    """특정 문제 수(체급)에 해당하는 랭킹만 조회"""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT 
            RANK() OVER (ORDER BY score DESC, time_taken ASC) as '순위',
            player_name as '이름', 
            (score || ' / ' || total_questions) as '점수',
            round(time_taken, 2) as '걸린 시간(초)', 
            datetime(played_at, 'localtime') as '날짜'
        FROM rankings 
        WHERE book_name = ? AND chapter = ? AND total_questions = ?
        ORDER BY score DESC, time_taken ASC 
    """, conn, params=(book, chapter, total_q))
    conn.close()
    return df

# --- 메인 앱 로직 ---
st.set_page_config(page_title="단어 스피드 게임", page_icon="⚡", layout="wide")

if 'stage' not in st.session_state:
    st.session_state['stage'] = 'setup'
if 'score' not in st.session_state:
    st.session_state['score'] = 0

create_rankings_table()

# [사이드바] 명예의 전당 (통합)
with st.sidebar:
    st.header("🏆 통합 챔피언 (전체 범위)")
    st.caption("가장 많은 단어를 맞힌 1등!")
    books_list = get_books()
    if books_list:
        for b in books_list:
            champ = get_book_champion(b)
            if champ:
                name, sc, tot = champ
                percent = int(sc * 100 / tot) if tot > 0 else 0
                st.info(f"**{b}**\n\n👑 {name}\n({sc}점 / {tot}문제)")
            else:
                st.caption(f"{b}: 아직 도전자가 없습니다.")
    else:
        st.write("단어장 데이터가 없습니다.")

st.title("⚡ 영어 단어 스피드 게임")

# 1. 설정 단계
if st.session_state['stage'] == 'setup':
    col1, col2 = st.columns(2)
    
    with col1:
        books = get_books()
        selected_book = st.selectbox("📘 단어장을 선택하세요", books)

    if selected_book:
        with col2:
            raw_chapters = get_chapters(selected_book)
            chapter_options = [0] + raw_chapters
            chapter_labels = ["전체 (ALL Chapters)"] + [f"Chapter {c}" for c in raw_chapters]
            
            selected_chapter_idx = st.selectbox(
                "bookmark 챕터를 선택하세요", 
                range(len(chapter_options)), 
                format_func=lambda x: chapter_labels[x]
            )
            selected_chapter = chapter_options[selected_chapter_idx]

        st.divider()
        
        st.subheader("⚙️ 시험 옵션 설정")
        opt_col1, opt_col2 = st.columns(2)
        
        with opt_col1:
            available_types = get_types(selected_book)
            if available_types:
                selected_types = st.multiselect(
                    "포함할 단어 유형 (비우면 모두 포함)", 
                    available_types, 
                    default=available_types
                )
            else:
                st.caption("유형 정보가 없는 단어장입니다. (전체 포함)")
                selected_types = None
        
        with opt_col2:
            max_words = st.number_input(
                "시험 볼 단어 수 (순위 경쟁을 위해 통일 추천)", 
                min_value=10, max_value=200, value=40, step=10
            )

        if st.button("🚀 게임 시작!", type="primary", use_container_width=True):
            words = get_words(selected_book, selected_chapter, selected_types)
            
            if words:
                if len(words) > max_words:
                    words = random.sample(words, max_words)
                else:
                    random.shuffle(words)
                
                st.session_state['words'] = words
                st.session_state['total_q'] = len(words)
                st.session_state['book'] = selected_book
                st.session_state['chapter'] = selected_chapter
                st.session_state['score'] = 0
                st.session_state['current_q'] = 0
                st.session_state['start_time'] = time.time()
                st.session_state['stage'] = 'playing'
                
                keys_to_remove = [k for k in st.session_state.keys() if k.startswith('options_')]
                for k in keys_to_remove:
                    del st.session_state[k]
                    
                st.rerun()
            else:
                st.error("선택한 조건에 해당하는 단어가 없습니다.")

# 2. 게임 진행 단계
elif st.session_state['stage'] == 'playing':
    idx = st.session_state['current_q']
    words = st.session_state['words']
    
    progress = (idx / st.session_state['total_q'])
    st.progress(progress, text=f"문제 {idx + 1} / {st.session_state['total_q']}")

    current_word = words[idx]
    english = current_word[0]
    correct_meaning = current_word[1]
    w_type = current_word[2]

    st.markdown(f"<h1 style='text-align: center; color: #2e86de;'>{english}</h1>", unsafe_allow_html=True)
    if w_type:
        st.markdown(f"<p style='text-align: center; color: gray;'>({w_type})</p>", unsafe_allow_html=True)
    else:
        st.write("")

    if f'options_{idx}' not in st.session_state:
        all_meanings = [w[1] for w in words]
        options = [correct_meaning]
        
        while len(options) < 4 and len(all_meanings) >= 4:
            wrong = random.choice(all_meanings)
            if wrong not in options:
                options.append(wrong)
        while len(options) < 4:
            options.append("오답 보기 부족")
            
        random.shuffle(options)
        st.session_state[f'options_{idx}'] = options
    
    options = st.session_state[f'options_{idx}']

    def check_answer(selected):
        if selected == correct_meaning:
            st.session_state['score'] += 1
            st.toast("⭕ 정답입니다!", icon="✅")
        else:
            st.toast(f"❌ 틀렸습니다. 정답: {correct_meaning}", icon="⚠️")
        time.sleep(0.5) 
        if st.session_state['current_q'] + 1 < st.session_state['total_q']:
            st.session_state['current_q'] += 1
        else:
            st.session_state['end_time'] = time.time()
            st.session_state['stage'] = 'finished'

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"1. {options[0]}", use_container_width=True):
            check_answer(options[0]); st.rerun()
        if st.button(f"2. {options[1]}", use_container_width=True):
            check_answer(options[1]); st.rerun()
    with col2:
        if st.button(f"3. {options[2]}", use_container_width=True):
            check_answer(options[2]); st.rerun()
        if st.button(f"4. {options[3]}", use_container_width=True):
            check_answer(options[3]); st.rerun()

# 3. 게임 종료
elif st.session_state['stage'] == 'finished':
    total_time = st.session_state['end_time'] - st.session_state['start_time']
    final_score = st.session_state['score']
    total_q = st.session_state['total_q']
    percent_score = int(final_score * 100 / total_q) if total_q > 0 else 0
    
    st.balloons()
    st.markdown(f"<h2 style='text-align: center;'>게임 종료!</h2>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align: center;'>{percent_score}% ({final_score} / {total_q})</h3>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center;'>걸린 시간: {total_time:.2f}초</p>", unsafe_allow_html=True)

    with st.form("ranking_form"):
        name = st.text_input("순위 등록을 위한 이름(닉네임):")
        submitted = st.form_submit_button("기록 저장하기")
        
        if submitted:
            if not name:
                st.warning("이름을 입력해주세요!")
            else:
                updated = save_score_if_best(
                    name, 
                    st.session_state['book'], 
                    st.session_state['chapter'], 
                    final_score, 
                    total_q, 
                    total_time
                )
                if updated:
                    st.success("기록이 저장되었습니다!")
                else:
                    st.info("기존 최고 기록보다 낮아 갱신되지 않았습니다.")
                
                st.session_state['stage'] = 'ranking'
                st.rerun()

# 4. 랭킹 확인 (수정됨: 체급별 필터링)
elif st.session_state['stage'] == 'ranking':
    chap_name = "전체 (All Chapters)" if st.session_state['chapter'] == 0 else f"Chapter {st.session_state['chapter']}"
    
    st.subheader(f"🏆 [{st.session_state['book']} - {chap_name}] 명예의 전당")
    
    # DB에 저장된 문제 수 목록 가져오기 (예: 10개, 40개, 100개 등)
    counts = get_existing_question_counts(st.session_state['book'], st.session_state['chapter'])
    
    if not counts:
        st.info("아직 등록된 랭킹이 없습니다.")
    else:
        # 방금 플레이한 문제 수가 있으면 그걸 기본값으로 선택
        current_q = st.session_state.get('total_q', 40)
        default_idx = 0
        if current_q in counts:
            default_idx = counts.index(current_q)
            
        selected_q_count = st.selectbox(
            "확인할 순위의 '문제 수(체급)'를 선택하세요:", 
            counts, 
            index=default_idx,
            format_func=lambda x: f"{x}단어 시험"
        )
        
        df = get_rankings(st.session_state['book'], st.session_state['chapter'], selected_q_count)
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    if st.button("처음으로 돌아가기"):
        st.session_state['stage'] = 'setup'
        st.rerun()