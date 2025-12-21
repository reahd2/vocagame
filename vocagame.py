import streamlit as st
import sqlite3
import random
import time
import pandas as pd

# DB 파일 이름 설정
DB_NAME = 'english_words_final.db'

# --- 데이터베이스 및 유틸리티 함수 ---
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def pick_random_meaning(text):
    """뜻 여러 개 중 하나 랜덤 선택"""
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
            total_questions INTEGER DEFAULT 0,
            time_taken REAL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # total_questions 컬럼이 없는 구버전 DB 호환성 처리
    cursor.execute("PRAGMA table_info(rankings)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'total_questions' not in columns:
        try:
            cursor.execute("ALTER TABLE rankings ADD COLUMN total_questions INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
            
    conn.commit()
    conn.close()

def clean_invalid_scores():
    """DB 정화 및 데이터 무결성 보장 함수"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 점수가 총 문제보다 큰 경우 수정
    cursor.execute("""
        UPDATE rankings 
        SET score = total_questions 
        WHERE score > total_questions AND total_questions > 0
    """)
    
    # 2. total_questions가 0이거나 NULL인 경우 score로 채움
    cursor.execute("""
        UPDATE rankings
        SET total_questions = score
        WHERE total_questions IS NULL OR total_questions = 0
    """)
    
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
    cursor.execute("SELECT DISTINCT chapter FROM words WHERE book_name = ? AND chapter != 0", (book_name,))
    raw_chapters = cursor.fetchall()
    conn.close()
    
    chapters = []
    for row in raw_chapters:
        try:
            chapters.append(int(row[0]))
        except (ValueError, TypeError):
            continue
            
    return sorted(list(set(chapters)))

def get_types(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT type FROM words WHERE book_name = ?", (book_name,))
    types = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return sorted([t for t in types if t])

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
    raw_words = cursor.fetchall()
    conn.close()
    
    processed_words = []
    for eng, kor, w_type, chap in raw_words:
        random_kor = pick_random_meaning(kor)
        processed_words.append((eng, random_kor, w_type, chap))
    return processed_words

def get_book_champion(book_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT player_name, score, total_questions 
        FROM rankings 
        WHERE book_name = ? AND chapter = 0 
        ORDER BY score DESC, total_questions DESC, time_taken ASC 
        LIMIT 1
    """, (book_name,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_score_if_best(name, book, chapter, score, total_q, time_taken):
    if score > total_q:
        score = total_q

    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, score, time_taken FROM rankings 
        WHERE player_name = ? AND book_name = ? AND chapter = ? AND total_questions = ?
    """, (name, book, chapter, total_q))
    row = cursor.fetchone()
    
    should_update = False
    
    if row:
        existing_id, old_score, old_time = row
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
            cursor.execute(f"""
                DELETE FROM rankings 
                WHERE book_name = ? AND chapter = ? AND total_questions = ? AND id NOT IN ({placeholders})
            """, (book, chapter, total_q, *top_10_ids))
            
    conn.commit()
    conn.close()
    return should_update

def get_existing_question_counts(book, chapter):
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
st.set_page_config(page_title="쑥쑥단어게임", page_icon="⚡", layout="wide")

create_rankings_table()
clean_invalid_scores()

if 'stage' not in st.session_state:
    st.session_state['stage'] = 'setup'
if 'score' not in st.session_state:
    st.session_state['score'] = 0

# [사이드바]
with st.sidebar:
    st.header("🏆 통합 챔피언 (전체 범위)")
    st.caption("가장 높은 점수와 가장 많은 문제를 푼 전설!")
    books_list = get_books()
    if books_list:
        for b in books_list:
            champ = get_book_champion(b)
            if champ:
                name, sc, tot = champ
                st.info(f"**{b}**\n\n👑 {name}\n({sc}점 / {tot}문제)")
            else:
                st.caption(f"{b}: 아직 도전자가 없습니다.")
    else:
        st.write("단어장 데이터가 없습니다.")

st.title("⚡쑥쑥단어게임")

# 1. 설정 단계
if st.session_state['stage'] == 'setup':
    col1, col2 = st.columns(2)
    
    with col1:
        books = get_books()
        selected_book = st.selectbox("📘 단어장을 선택하세요", books)

    if selected_book:
        with col2:
            chapters = get_chapters(selected_book)
            if not chapters:
                st.error("이 책에는 챕터 정보가 없습니다.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    start_chapter = st.selectbox("시작 챕터 (Start)", chapters, index=0)
                with c2:
                    end_chapter = st.selectbox("끝 챕터 (End)", chapters, index=len(chapters)-1)
        
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
            selected_count_opt = st.radio(
                "시험 볼 단어 수",
                ["10개", "20개", "40개", "전체"],
                horizontal=True,
                index=1 
            )

        if not chapters:
            st.warning("데이터가 부족합니다.")
        elif start_chapter > end_chapter:
            st.error("⚠️ 시작 챕터가 끝 챕터보다 클 수 없습니다.")
        else:
            words_in_range = get_words_by_range(selected_book, start_chapter, end_chapter, selected_types)
            total_available = len(words_in_range)
            
            if total_available == 0:
                st.warning("선택한 범위에 단어가 없습니다.")
            else:
                st.write("") # 여백
                st.info(f"✅ 선택 범위(Ch.{start_chapter}~Ch.{end_chapter})에서 총 {total_available}개의 단어가 검색되었습니다.")
                
                # [수정] 버튼을 컬럼 밖으로 꺼내서 넓게 배치
                st.divider()
                if st.button("🚀 게임 시작!", type="primary", use_container_width=True):
                    
                    if selected_count_opt == "전체":
                        target_count = total_available
                    else:
                        target_count = int(selected_count_opt.replace("개", ""))
                    
                    if total_available < target_count:
                        st.toast(f"⚠️ 단어가 부족하여 {total_available}문제(전체)로 진행합니다.", icon="ℹ️")
                        final_words = words_in_range
                        random.shuffle(final_words)
                    else:
                        final_words = random.sample(words_in_range, target_count)
                    
                    st.session_state['words'] = final_words
                    st.session_state['total_q'] = len(final_words)
                    st.session_state['book'] = selected_book
                    
                    # 챔피언 여부 판별
                    min_chap = min(chapters)
                    max_chap = max(chapters)
                    
                    if start_chapter == min_chap and end_chapter == max_chap:
                        st.session_state['chapter'] = 0
                        st.session_state['rank_label'] = "전체 (Integrated Champion)"
                    elif start_chapter == end_chapter:
                        st.session_state['chapter'] = start_chapter
                        st.session_state['rank_label'] = f"Chapter {start_chapter}"
                    else:
                        st.session_state['chapter'] = -1
                        st.session_state['rank_label'] = f"커스텀 범위 (Ch.{start_chapter}~{end_chapter})"
                        
                    st.session_state['score'] = 0
                    st.session_state['current_q'] = 0
                    st.session_state['start_time'] = time.time()
                    st.session_state['solved_indexes'] = set()
                    st.session_state['stage'] = 'playing'
                    
                    # 기존 옵션 키 삭제
                    keys_to_remove = [k for k in st.session_state.keys() if k.startswith('options_')]
                    for k in keys_to_remove:
                        del st.session_state[k]
                    
                    st.rerun()

# 2. 게임 진행 단계 (버튼 멈춤 해결 & 디자인 개선)
elif st.session_state['stage'] == 'playing':
    idx = st.session_state['current_q']
    words = st.session_state['words']
    
    # 정답 처리를 위한 콜백 함수
    def submit_answer(selected):
        if idx in st.session_state['solved_indexes']:
            return

        st.session_state['solved_indexes'].add(idx)
        
        current_w = st.session_state['words'][idx]
        correct_mean = current_w[1]
        
        if selected == correct_mean:
            st.session_state['score'] += 1
            st.toast("⭕ 정답입니다!", icon="✅")
        else:
            st.toast(f"❌ 틀렸습니다. 정답: {correct_mean}", icon="⚠️")
        
        # 다음 문제로 넘어가거나 종료
        if st.session_state['current_q'] + 1 < st.session_state['total_q']:
            st.session_state['current_q'] += 1
        else:
            st.session_state['end_time'] = time.time()
            st.session_state['stage'] = 'finished'

    progress = (idx / st.session_state['total_q'])
    st.progress(progress, text=f"문제 {idx + 1} / {st.session_state['total_q']}")

    current_word = words[idx]
    english = current_word[0]
    correct_meaning = current_word[1]
    w_type = current_word[2]
    w_chapter = current_word[3]

    st.markdown(f"<h1 style='text-align: center; color: #2e86de;'>{english}</h1>", unsafe_allow_html=True)
    if w_type:
        st.markdown(f"<p style='text-align: center; color: gray;'>({w_type} / Ch.{w_chapter})</p>", unsafe_allow_html=True)
    else:
        st.write("")

    if f'options_{idx}' not in st.session_state:
        all_meanings = [w[1] for w in words]
        options = [correct_meaning]
        
        loop_count = 0
        while len(options) < 4:
            loop_count += 1
            if len(all_meanings) > 1:
                wrong = random.choice(all_meanings)
                if wrong not in options:
                    options.append(wrong)
            else:
                options.append("오답 데이터 부족")
            
            if loop_count > 20: 
                while len(options) < 4: options.append("...")
                break
            
        random.shuffle(options)
        st.session_state[f'options_{idx}'] = options
    
    options = st.session_state[f'options_{idx}']

    # 보기 버튼 배치
    col1, col2 = st.columns(2)
    with col1:
        st.button(f"1. {options[0]}", use_container_width=True, key=f"btn_{idx}_0", on_click=submit_answer, args=(options[0],))
        st.button(f"2. {options[1]}", use_container_width=True, key=f"btn_{idx}_1", on_click=submit_answer, args=(options[1],))
    with col2:
        st.button(f"3. {options[2]}", use_container_width=True, key=f"btn_{idx}_2", on_click=submit_answer, args=(options[2],))
        st.button(f"4. {options[3]}", use_container_width=True, key=f"btn_{idx}_3", on_click=submit_answer, args=(options[3],))

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
        st.write(f"**랭킹 등록 구간: {st.session_state.get('rank_label', 'Unknown')}**")
        st.caption(f"문제 수 체급: {total_q}문제")
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
                    st.info("기존 최고 기록(동일 문제수 내)보다 낮아 갱신되지 않았습니다.")
                
                st.session_state['stage'] = 'ranking'
                st.rerun()

# 4. 랭킹 확인
elif st.session_state['stage'] == 'ranking':
    chap_code = st.session_state['chapter']
    if chap_code == 0:
        chap_display = "🏆 통합 챔피언 (전체 범위)"
    elif chap_code == -1:
        chap_display = "🛠️ 커스텀/부분 범위"
    else:
        chap_display = f"Chapter {chap_code}"
    
    st.subheader(f"📊 [{st.session_state['book']} - {chap_display}] 명예의 전당")
    
    counts = get_existing_question_counts(st.session_state['book'], st.session_state['chapter'])
    
    if not counts:
        st.info("이 구간에는 아직 등록된 랭킹이 없습니다.")
    else:
        current_q = st.session_state.get('total_q', 20)
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
