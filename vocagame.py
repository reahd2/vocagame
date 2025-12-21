# 2. 게임 진행 단계 (수정됨)
elif st.session_state['stage'] == 'playing':
    idx = st.session_state['current_q']
    words = st.session_state['words']
    
    # 정답 처리를 위한 콜백 함수 (버튼 클릭 시 먼저 실행됨)
    def submit_answer(selected):
        # 이미 푼 문제라면 패스 (중복 클릭 방지)
        if idx in st.session_state['solved_indexes']:
            return

        st.session_state['solved_indexes'].add(idx)
        
        # 정답 확인
        current_w = st.session_state['words'][idx]
        correct_mean = current_w[1]
        
        if selected == correct_mean:
            st.session_state['score'] += 1
            st.toast("⭕ 정답입니다!", icon="✅")
        else:
            st.toast(f"❌ 틀렸습니다. 정답: {correct_mean}", icon="⚠️")
        
        # 다음 문제로 인덱스 증가
        if st.session_state['current_q'] + 1 < st.session_state['total_q']:
            st.session_state['current_q'] += 1
        else:
            # 마지막 문제였으면 종료 처리
            st.session_state['end_time'] = time.time()
            st.session_state['stage'] = 'finished'

    # 진행률 표시
    progress = (idx / st.session_state['total_q'])
    st.progress(progress, text=f"문제 {idx + 1} / {st.session_state['total_q']}")

    current_word = words[idx]
    english = current_word[0]
    correct_meaning = current_word[1]
    w_type = current_word[2]
    w_chapter = current_word[3]

    # 문제 표시
    st.markdown(f"<h1 style='text-align: center; color: #2e86de;'>{english}</h1>", unsafe_allow_html=True)
    if w_type:
        st.markdown(f"<p style='text-align: center; color: gray;'>({w_type} / Ch.{w_chapter})</p>", unsafe_allow_html=True)
    else:
        st.write("")

    # 보기 생성 (이미 생성된 보기가 없으면 새로 생성)
    if f'options_{idx}' not in st.session_state:
        all_meanings = [w[1] for w in words]
        options = [correct_meaning]
        
        # 오답 채우기
        loop_count = 0
        while len(options) < 4:
            loop_count += 1
            if len(all_meanings) > 1:
                wrong = random.choice(all_meanings)
                if wrong not in options:
                    options.append(wrong)
            else:
                options.append("오답 데이터 부족")
            
            # 무한 루프 방지
            if loop_count > 20: 
                while len(options) < 4: options.append("...")
                break
            
        random.shuffle(options)
        st.session_state[f'options_{idx}'] = options
    
    options = st.session_state[f'options_{idx}']

    # [핵심 수정] 버튼 배치
    # key에 idx(문제번호)를 포함시켜서 매 문제마다 새로운 버튼으로 인식하게 함
    col1, col2 = st.columns(2)
    
    with col1:
        st.button(
            f"1. {options[0]}", 
            use_container_width=True, 
            key=f"btn_{idx}_0",  # 고유 키
            on_click=submit_answer, 
            args=(options[0],)
        )
        st.button(
            f"2. {options[1]}", 
            use_container_width=True, 
            key=f"btn_{idx}_1", 
            on_click=submit_answer, 
            args=(options[1],)
        )
    with col2:
        st.button(
            f"3. {options[2]}", 
            use_container_width=True, 
            key=f"btn_{idx}_2", 
            on_click=submit_answer, 
            args=(options[2],)
        )
        st.button(
            f"4. {options[3]}", 
            use_container_width=True, 
            key=f"btn_{idx}_3", 
            on_click=submit_answer, 
            args=(options[3],)
        )
