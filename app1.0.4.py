import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import sys
import os
import subprocess

# ==========================================
# 初期設定
# ==========================================
# スマホ閲覧を意識し、サイドバーは初期状態で閉じる設定にします
st.set_page_config(page_title="Travel App", layout="centered", initial_sidebar_state="collapsed")

# ==========================================
# スプレッドシート連携関数
# ==========================================
@st.cache_resource
def get_gspread_client():
    """スプレッドシートAPIクライアントを初期化してキャッシュする"""
    # secrets.tomlから認証情報を取得
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=600) # 10分間データをキャッシュ（通信回数削減のため）
def load_data(sheet_name):
    """指定したシート名のデータをDataFrameとして読み込む"""
    try:
        client = get_gspread_client()
        # secrets.tomlからスプレッドシートIDを取得して開く
        sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")
        return pd.DataFrame()

# データを更新する際は、キャッシュをクリアする必要があります
def clear_cache():
    st.cache_data.clear()

# ==========================================
# 状態管理 (Session State)
# ==========================================
if 'is_shared_view' not in st.session_state:
    st.session_state.is_shared_view = False

# どの画面を表示しているかを管理する変数
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'start'

# 選択された年や旅行IDを保持する変数
if 'selected_year' not in st.session_state:
    st.session_state.selected_year = None
if 'selected_travel_id' not in st.session_state:
    st.session_state.selected_travel_id = None
if 'selected_date' not in st.session_state:
    st.session_state.selected_date = None

def navigate_to(page_name):
    """画面遷移用関数"""
    if st.session_state.is_shared_view:
        allowed_pages = ['day_list', 'timeline', 'schedule_detail']
        if page_name not in allowed_pages:
            st.warning("共有（閲覧専用）モードではこの操作は許可されていません。")
            return
    st.session_state.current_page = page_name
    st.rerun()

# ==========================================
# 画面ごとの描画関数 (UI骨格)
# ==========================================
def render_start():
    st.title("旅行アプリ (Start)")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("新規旅行登録", use_container_width=True):
            navigate_to('register_travel')
    with col2:
        if st.button("既存の旅行 (年一覧へ)", use_container_width=True):
            navigate_to('year_list')

def render_register_travel():
    st.title("旅行登録")
    
    with st.form("register_form"):
        title = st.text_input("旅行タイトル")
        start_date = st.date_input("出発日")
        end_date = st.date_input("帰着日")
        member_count = st.number_input("メンバー数", min_value=1, value=2)
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("登録して日一覧へ", use_container_width=True)
        with col2:
            if st.form_submit_button("戻る", use_container_width=True):
                 navigate_to('start')

    if submitted:
        if not title:
            st.error("タイトルを入力してください")
        else:
            try:
                client = get_gspread_client()
                sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
                worksheet = sh.worksheet("Travel")
                
                df_travel = load_data('Travel')
                new_id = 1 if df_travel.empty else int(df_travel['トラベルナンバー'].max()) + 1
                
                worksheet.append_row([
                    new_id, 
                    title, 
                    start_date.strftime("%Y/%m/%d"), 
                    end_date.strftime("%Y/%m/%d")
                ])
                
                st.success(f"「{title}」を登録しました！")
                clear_cache()
                
                st.session_state.selected_travel_id = new_id
                navigate_to('day_list')
            except Exception as e:
                st.error(f"保存に失敗しました: {e}")

def render_year_list():
    st.title("年一覧")
    
    if st.button("← スタートへ戻る"):
        navigate_to('start')
        
    df_travel = load_data('Travel')
    if not df_travel.empty:
        df_travel['年'] = pd.to_datetime(df_travel['出発日']).dt.year
        years = sorted(df_travel['年'].unique())
        
        st.subheader("登録されている年")
        for year in years:
            if st.button(f"{year}年の旅行", key=f"year_{year}", use_container_width=True):
                st.session_state.selected_year = year
                navigate_to('travel_list')
    else:
        st.info("旅行データがまだありません。")

def render_travel_list():
    st.title(f"{st.session_state.selected_year}年の旅行一覧")
    
    if st.button("← 年一覧へ戻る"):
        st.session_state.selected_year = None
        navigate_to('year_list')
        
    df_travel = load_data('Travel')
    if not df_travel.empty:
        df_travel['年'] = pd.to_datetime(df_travel['出発日']).dt.year
        target_travels = df_travel[df_travel['年'] == st.session_state.selected_year]
        
        for index, row in target_travels.iterrows():
            if st.button(f"{row['タイトル']}", key=f"travel_{row['トラベルナンバー']}", use_container_width=True):
                st.session_state.selected_travel_id = row['トラベルナンバー']
                navigate_to('day_list')

def render_day_list():
    travel_id = st.session_state.selected_travel_id
    df_travel = load_data('Travel')
    
    if df_travel.empty or travel_id not in df_travel['トラベルナンバー'].values:
        st.error("旅行データが見つかりません。")
        if not st.session_state.is_shared_view:
            if st.button("← 旅行一覧へ戻る"):
                st.session_state.selected_travel_id = None
                navigate_to('travel_list')
        return
        
    travel_row = df_travel[df_travel['トラベルナンバー'] == travel_id].iloc[0]
    st.title(f"{travel_row['タイトル']} - 日一覧")
    
    # 共有モード時は戻るボタンや登録ボタンを隠す
    if not st.session_state.is_shared_view:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("← 旅行一覧へ戻る"):
                st.session_state.selected_travel_id = None
                navigate_to('travel_list')
        with col2:
            if st.button("メンバー登録", use_container_width=True):
                navigate_to('register_member')
        with col3:
            if st.button("日程変更", type="primary", use_container_width=True):
                st.warning("日程変更機能は未実装です")
        with col4:
            if st.button("🔗 共有URL発行", use_container_width=True):
                st.session_state.show_share_modal = True
                
        # 共有URL発行用の表示エリア
        if st.session_state.get('show_share_modal', False):
            # 現在のアプリのベースURL（QueryParamsを除いたもの、またはホスト名）を取得
            base_url = st.get_option("server.baseUrlPath") or ""
            # Streamlit Community Cloud等で動いている場合の現在のURLを取得する簡易的な仕組み
            # クエリパラメータ付きのURLを生成
            current_url = window_location_url = f"{st.context.headers.get('Origin', '')}/?view_travel={travel_id}"
            st.info("👇 以下のURLをコピーしてメンバーに共有してください（閲覧専用）")
            st.code(current_url, language="text")
    else:
        st.info("📌 メンバー閲覧専用モードで表示しています。")
            
    # --- 旅行全体の金額集計処理 ---
    df_money = load_data('Money')
    df_sched = load_data('Schedule')
    df_sub = load_data('Sub_Schedule')
    df_member = load_data('Member')
    
    total_travel_money = 0
    daily_summary = {}   # {日付文字列: 金額}
    member_summary = {}  # {メンバー名: 金額}
    cat_summary = {      # {分類名: 金額}
        '移動': 0,
        '活動': 0,
        '食事': 0,
        '宿泊': 0,
        'その他': 0
    }
    
    start_date = pd.to_datetime(travel_row['出発日'])
    end_date = pd.to_datetime(travel_row['帰着日'])
    date_range = pd.date_range(start=start_date, end=end_date)
    
    for d in date_range:
        daily_summary[d.strftime("%Y/%m/%d")] = 0

    if not df_money.empty and 'トラベルナンバー' in df_money.columns:
        df_m = df_money[df_money['トラベルナンバー'] == travel_id].copy()
        if not df_m.empty:
            df_m['金額'] = pd.to_numeric(df_m['金額'], errors='coerce').fillna(0)
            total_travel_money = df_m['金額'].sum()
            
            for _, m_row in df_m.iterrows():
                m_num = m_row.get('メンバーナンバー')
                amt = m_row.get('金額', 0)
                
                m_name = f"メンバー {m_num}"
                if not df_member.empty and 'トラベルナンバー' in df_member.columns and 'メンバーナンバー' in df_member.columns and '名前' in df_member.columns:
                    matched = df_member[(df_member['トラベルナンバー'] == travel_id) & (df_member['メンバーナンバー'] == m_num)]
                    if not matched.empty:
                        m_name = matched.iloc[0]['名前']
                        
                member_summary[m_name] = member_summary.get(m_name, 0) + amt
                
            for _, m_row in df_m.iterrows():
                s_num = m_row.get('スケジュールナンバー')
                sub_num = m_row.get('サブスケジュールナンバー')
                amt = m_row.get('金額', 0)
                
                is_sub = pd.notna(sub_num) and str(sub_num).strip() != ''
                s_date_str = None
                s_cat = 'その他'
                
                if is_sub:
                    if not df_sub.empty:
                        try:
                            s_match = df_sub[(df_sub['トラベルナンバー'] == travel_id) & 
                                             (df_sub['スケジュールナンバー'] == int(float(s_num))) & 
                                             (df_sub['サブスケジュールナンバー'] == int(float(sub_num)))]
                            if not s_match.empty:
                                start_dt = pd.to_datetime(s_match.iloc[0]['サブスケジュール開始時間'])
                                s_date_str = start_dt.strftime("%Y/%m/%d")
                                s_cat = s_match.iloc[0].get('スケジュール分類', 'その他')
                        except:
                            pass
                else:
                    if not df_sched.empty:
                        try:
                            s_match = df_sched[(df_sched['トラベルナンバー'] == travel_id) & 
                                               (df_sched['スケジュールナンバー'] == int(float(s_num)))]
                            if not s_match.empty:
                                start_dt = pd.to_datetime(s_match.iloc[0]['スケジュール開始時間'])
                                s_date_str = start_dt.strftime("%Y/%m/%d")
                                s_cat = s_match.iloc[0].get('スケジュール分類', 'その他')
                        except:
                            pass
                            
                if s_date_str in daily_summary:
                    daily_summary[s_date_str] += amt
                    
                if s_cat in cat_summary:
                    cat_summary[s_cat] += amt
                else:
                    cat_summary['その他'] += amt

    st.info(f"💰 旅行全体の合計金額: {total_travel_money:,.0f}円")
    
    if total_travel_money > 0:
        with st.expander("明細を見る"):
            st.markdown("#### 日ごとの明細")
            for d in date_range:
                full_date = d.strftime("%Y/%m/%d")
                day_diff = (d - start_date).days + 1
                amt = daily_summary.get(full_date, 0)
                col_d, col_a = st.columns([3, 1])
                with col_d:
                    st.write(f"{d.month}/{d.day} ({day_diff}日目)")
                with col_a:
                    st.write(f"{amt:,.0f}円")
                    
            st.markdown("---")
            st.markdown("#### 分類ごとの明細")
            for cat_name, amt in cat_summary.items():
                col_c, col_a = st.columns([3, 1])
                with col_c:
                    st.write(cat_name)
                with col_a:
                    st.write(f"{amt:,.0f}円")
                    
            st.markdown("---")
            st.markdown("#### 支払者明細")
            for m_name, amt in member_summary.items():
                col_m, col_a = st.columns([3, 1])
                with col_m:
                    st.write(m_name)
                with col_a:
                    st.write(f"{amt:,.0f}円")

    st.write("") 
    
    for d in date_range:
        full_date = d.strftime("%Y/%m/%d")
        day_diff = (d - start_date).days + 1
        
        if st.button(f"{d.month}/{d.day} ({day_diff}日目)", key=f"date_{full_date}", use_container_width=True):
            st.session_state.selected_date = d.date()
            navigate_to('timeline')


def render_timeline():
    travel_id = st.session_state.selected_travel_id
    df_travel = load_data('Travel')
    travel_row = df_travel[df_travel['トラベルナンバー'] == travel_id].iloc[0]
    travel_start = pd.to_datetime(travel_row['出発日']).date()

    if st.session_state.selected_date is None:
        st.session_state.selected_date = travel_start

    target_date = pd.to_datetime(st.session_state.selected_date).date()
    
    travel_row = df_travel[df_travel['トラベルナンバー'] == travel_id].iloc[0]
    travel_start = pd.to_datetime(travel_row['出発日']).date()
    travel_end = pd.to_datetime(travel_row['帰着日']).date()
    
    prev_date = target_date - pd.Timedelta(days=1)
    next_date = target_date + pd.Timedelta(days=1)
    
    has_prev = prev_date >= travel_start
    has_next = next_date <= travel_end
    
    df_sched = load_data('Schedule')
    df_sub = load_data('Sub_Schedule')
    
    day_start = pd.Timestamp(target_date)
    day_end = day_start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    
    if not df_sched.empty and 'スケジュール開始時間' in df_sched.columns:
        df_sched = df_sched[df_sched['トラベルナンバー'] == travel_id]
        df_sched['開始'] = pd.to_datetime(df_sched['スケジュール開始時間'])
        df_sched['終了'] = pd.to_datetime(df_sched['スケジュール終了時間'])
        df_sched = df_sched[(df_sched['開始'] <= day_end) & (df_sched['終了'] > day_start)]
        
    if not df_sub.empty and 'サブスケジュール開始時間' in df_sub.columns:
        df_sub = df_sub[df_sub['トラベルナンバー'] == travel_id]
        df_sub['開始'] = pd.to_datetime(df_sub['サブスケジュール開始時間'])
        df_sub['終了'] = pd.to_datetime(df_sub['サブスケジュール終了時間'])
        df_sub = df_sub[(df_sub['開始'] <= day_end) & (df_sub['終了'] > day_start)]

    df_money = load_data('Money')
    daily_total = 0
    daily_details = []
    
    if not df_money.empty and 'トラベルナンバー' in df_money.columns:
        df_m = df_money[df_money['トラベルナンバー'] == travel_id].copy()
        if not df_m.empty:
            df_m['金額'] = pd.to_numeric(df_m['金額'], errors='coerce').fillna(0)
            
            valid_sched = df_sched[(df_sched['開始'] >= day_start) & (df_sched['開始'] <= day_end)] if not df_sched.empty else pd.DataFrame()
            sched_nums = valid_sched['スケジュールナンバー'].tolist() if not valid_sched.empty and 'スケジュールナンバー' in valid_sched.columns else []
            
            is_main = df_m['スケジュールナンバー'].isin(sched_nums) & (df_m['サブスケジュールナンバー'].isna() | (df_m['サブスケジュールナンバー'].astype(str).str.strip() == ''))
            
            is_sub = False
            if not df_sub.empty and 'スケジュールナンバー' in df_sub.columns and 'サブスケジュールナンバー' in df_sub.columns:
                valid_sub = df_sub[(df_sub['開始'] >= day_start) & (df_sub['開始'] <= day_end)]
                valid_subs = set(zip(valid_sub['スケジュールナンバー'].astype(int), valid_sub['サブスケジュールナンバー'].astype(int)))
                sub_match_mask = []
                for _, r in df_m.iterrows():
                    try:
                        s_n = int(r['スケジュールナンバー'])
                        sub_n = int(r['サブスケジュールナンバー'])
                        sub_match_mask.append((s_n, sub_n) in valid_subs)
                    except:
                        sub_match_mask.append(False)
                is_sub = pd.Series(sub_match_mask, index=df_m.index)
                
            matched_money = df_m[is_main | is_sub]
            daily_total = matched_money['金額'].sum()

            if not matched_money.empty:
                df_sched_all = load_data('Schedule')
                df_sub_all = load_data('Sub_Schedule')
                
                aggregated_money = {}
                for _, m_row in matched_money.iterrows():
                    s_num = m_row['スケジュールナンバー']
                    sub_num = m_row['サブスケジュールナンバー']
                    amount = float(m_row['金額']) if pd.notna(m_row['金額']) else 0
                    
                    is_sub_item = pd.notna(sub_num) and str(sub_num).strip() != ''
                    key = (s_num, sub_num if is_sub_item else None)
                    
                    if key in aggregated_money:
                        aggregated_money[key] += amount
                    else:
                        aggregated_money[key] = amount

                for (s_num, sub_num), amount in aggregated_money.items():
                    title = "不明なスケジュール"
                    start_time = "99:99" 
                    
                    is_sub_item = sub_num is not None
                    
                    if is_sub_item:
                        try:
                            sub_n_int = int(float(sub_num))
                            s_n_int = int(float(s_num))
                            if not df_sub_all.empty:
                                sub_match = df_sub_all[(df_sub_all['スケジュールナンバー'] == s_n_int) & (df_sub_all['サブスケジュールナンバー'] == sub_n_int)]
                                if not sub_match.empty:
                                    title = sub_match.iloc[0].get('サブスケジュールタイトル', 'タイトルなし')
                                    start_time = str(sub_match.iloc[0].get('サブスケジュール開始時間', '99:99'))
                        except:
                            pass
                    else:
                        try:
                            s_n_int = int(float(s_num))
                            if not df_sched_all.empty:
                                sched_match = df_sched_all[df_sched_all['スケジュールナンバー'] == s_n_int]
                                if not sched_match.empty:
                                    title = sched_match.iloc[0].get('スケジュールタイトル', 'タイトルなし')
                                    start_time = str(sched_match.iloc[0].get('スケジュール開始時間', '99:99'))
                        except:
                            pass
                            
                    try:
                        s_sort = int(float(s_num)) if pd.notna(s_num) and str(s_num).strip() != '' else 0
                    except:
                        s_sort = 0
                        
                    try:
                        sub_sort = int(float(sub_num)) if is_sub_item else 0
                    except:
                        sub_sort = 0
                        
                    daily_details.append({
                        'title': title,
                        'amount': amount,
                        'start_time': start_time,
                        's_num': s_sort,
                        'sub_num': sub_sort
                    })
                
                daily_details.sort(key=lambda x: (x['start_time'], x['s_num'], x['sub_num']))

    st.title(f"タイムライン: {st.session_state.selected_date}")
    
    if st.button("← 日一覧へ戻る"):
        navigate_to('day_list')
        
    st.info(f"💰 この日の合計金額: {daily_total:,.0f}円")
    
    if daily_total > 0 and daily_details:
        with st.expander("明細を見る"):
            for item in daily_details:
                col_t, col_a = st.columns([3, 1])
                with col_t:
                    st.write(item['title'])
                with col_a:
                    st.write(f"{item['amount']:,.0f}円")

    # 共有モード時は新規スケジュール作成ボタンを隠す
    if not st.session_state.is_shared_view:
        if st.button("➕ 新規スケジュール登録", use_container_width=True, type="primary"):
            navigate_to('create_schedule')

    offset_list = []
    
    if not df_sched.empty:
        df_sched = df_sched.sort_values(by='開始')
        for _, row in df_sched.iterrows():
            start = pd.to_datetime(row['スケジュール開始時間'])
            end = pd.to_datetime(row['スケジュール終了時間'])
            
            start_clip = max(start, day_start)
            end_clip = min(end, day_end)
            
            s_min = start_clip.hour * 60 + start_clip.minute
            e_min = end_clip.hour * 60 + end_clip.minute
            
            orig_h = max(0, e_min - s_min)
            draw_h = orig_h
            if draw_h < 10:
                draw_h = 15
                
            delta_h = draw_h - orig_h
            extra_px = delta_h * 2
            
            if extra_px > 0:
                offset_list.append((e_min, extra_px))

    if not df_sub.empty:
        df_sub = df_sub.sort_values(by='開始')
        for _, row in df_sub.iterrows():
            start = pd.to_datetime(row['サブスケジュール開始時間'])
            end = pd.to_datetime(row['サブスケジュール終了時間'])
            
            start_clip = max(start, day_start)
            end_clip = min(end, day_end)
            
            s_min = start_clip.hour * 60 + start_clip.minute
            e_min = end_clip.hour * 60 + end_clip.minute
            
            orig_h = max(0, e_min - s_min)
            draw_h = orig_h
            if draw_h < 10:
                draw_h = 15
                
            delta_h = draw_h - orig_h
            extra_px = delta_h * 2
            
            if extra_px > 0:
                offset_list.append((e_min, extra_px))

    offset_list.sort(key=lambda x: x[0])

    def get_adjusted_top(minute_val):
        base_top = minute_val * 2
        accumulated_offset = sum(px for t, px in offset_list if t <= minute_val)
        return base_top + accumulated_offset

    total_container_height = get_adjusted_top(1440)

    st.markdown(f"""
        <style>
        .timeline-container {{
            position: relative;
            height: {total_container_height}px;
            background-color: #fcfcfc;
            width: 100%;
            border-left: 50px solid #e9ecef;
            border-radius: 5px;
            margin-top: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }}
        .time-label {{
            position: absolute;
            left: -45px;
            font-size: 12px;
            color: #6c757d;
        }}
        .time-grid-line {{
            position: absolute;
            left: 0;
            right: 0;
            height: 1px;
            background-color: #e0e0e0;
        }}
        .schedule-block {{
            position: absolute;
            left: 10px;
            right: 10px;
            border-radius: 5px;
            padding: 4px 8px;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
            word-break: break-all;
            white-space: normal;
            border-left: 5px solid #444;
        }}
        .schedule-block a {{
            text-decoration: none;
            color: inherit;
            display: block;
            height: 100%;
            transition: filter 0.2s;
        }}
        .schedule-block a:hover {{ filter: brightness(0.95); }}
        
        .sub-schedule-block {{
            position: absolute;
            left: 241.85px;
            right: 5px;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            word-break: break-all;
            white-space: normal;
            border-left: 4px solid #666;
            z-index: 10;
        }}
        .sub-schedule-block a {{
            text-decoration: none;
            color: inherit;
            display: block;
            height: 100%;
            transition: filter 0.2s;
        }}
        .sub-schedule-block a:hover {{ filter: brightness(0.95); }}   

        .cat-移動 {{ background-color: #E6F3FF; border-left-color: #0066CC; }}
        .cat-活動 {{ background-color: #FFE6E6; border-left-color: #CC0000; }}
        .cat-食事 {{ background-color: #FFF2E6; border-left-color: #CC6600; }}
        .cat-宿泊 {{ background-color: #E6E6FA; border-left-color: #6600CC; }}
        .cat-その他 {{ background-color: #F2F2F2; border-left-color: #666666; }}
        
        .empty-slot {{
            position: absolute;
            left: 10px;
            right: 10px;
            background-color: rgba(200, 200, 200, 0.15);
            border: 2px dashed #bbb;
            border-radius: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #888;
            font-size: 13px;
            font-weight: bold;
        }}
        </style>
    """, unsafe_allow_html=True)

    col_prev, col_next = st.columns(2)
    with col_prev:
        if has_prev and st.button(f"← {prev_date.strftime('%m/%d')} に移動", use_container_width=True):
            st.session_state.selected_date = prev_date
            st.rerun()
    with col_next:
        if has_next and st.button(f"{next_date.strftime('%m/%d')} に移動 →", use_container_width=True):
            st.session_state.selected_date = next_date
            st.rerun()

    html_content = '<div class="timeline-container">'
    
    for h in range(25):
        m = h * 60
        top = get_adjusted_top(m)
        html_content += f'<div class="time-label" style="top: {top-8}px;">{h}:00</div>'
        html_content += f'<div class="time-grid-line" style="top: {top}px;"></div>'

    occupied_intervals = [] 

    if not df_sched.empty:
        for _, row in df_sched.iterrows():
            start = pd.to_datetime(row['スケジュール開始時間'])
            end = pd.to_datetime(row['スケジュール終了時間'])
            
            start_clip = max(start, day_start)
            end_clip = min(end, day_end)
            
            s_min = start_clip.hour * 60 + start_clip.minute
            e_min = end_clip.hour * 60 + end_clip.minute
            
            orig_h = max(0, e_min - s_min)
            draw_h = orig_h
            if draw_h < 10:
                draw_h = 15
            
            top = get_adjusted_top(s_min)
            bottom = get_adjusted_top(s_min + draw_h)
            height = bottom - top
            
            occupied_intervals.append((top, bottom))
            
            cat = row['スケジュール分類'] if pd.notna(row['スケジュール分類']) else 'その他'
            title = row['スケジュールタイトル']
            time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
            
            sched_id = row['スケジュールナンバー']
            if st.session_state.is_shared_view:
                href = f"?detail_id={sched_id}&type=main&travel_id={travel_id}&view_travel={travel_id}"
            else:
                href = f"?detail_id={sched_id}&type=main&travel_id={travel_id}"
            
            html_content += f'<div id="sched_{sched_id}" class="schedule-block cat-{cat}" style="top: {top}px; height: {height}px;">'
            html_content += f'<a href="{href}" target="_self">'
            html_content += f'<div style="font-weight:bold; margin-bottom:2px;">{time_str}</div><div>{title}</div>'
            html_content += '</a>'
            
            if not df_sub.empty and 'スケジュールナンバー' in df_sub.columns:
                subs = df_sub[df_sub['スケジュールナンバー'] == row['スケジュールナンバー']]
                for sub_index, sub_row in subs.iterrows():
                    s_start = pd.to_datetime(sub_row['サブスケジュール開始時間'])
                    s_end = pd.to_datetime(sub_row['サブスケジュール終了時間'])
                    
                    s_start_clip = max(s_start, day_start)
                    s_end_clip = min(s_end, day_end)
                    
                    sub_s_min = s_start_clip.hour * 60 + s_start_clip.minute
                    sub_e_min = s_end_clip.hour * 60 + s_end_clip.minute
                    sub_orig_h = max(0, sub_e_min - sub_s_min)
                    sub_draw_h = sub_orig_h
                    if sub_draw_h < 10:
                        sub_draw_h = 15
                        
                    sub_top_abs = get_adjusted_top(sub_s_min)
                    sub_bottom_abs = get_adjusted_top(sub_s_min + sub_draw_h)
                    sub_top_rel = sub_top_abs - top
                    sub_height = sub_bottom_abs - sub_top_abs
                    
                    s_cat = sub_row['スケジュール分類'] if pd.notna(sub_row['スケジュール分類']) else 'その他'
                    s_time_str = f"{s_start.strftime('%H:%M')}-{s_end.strftime('%H:%M')}"
                    
                    sub_id = sub_row.get('サブスケジュールナンバー', sub_index)
                    if st.session_state.is_shared_view:
                        s_href = f"?detail_id={sub_id}&type=sub&travel_id={travel_id}&parent_sched={sched_id}&view_travel={travel_id}"
                    else:
                        s_href = f"?detail_id={sub_id}&type=sub&travel_id={travel_id}&parent_sched={sched_id}"
                    
                    html_content += f'<div id="sub_{sub_id}" class="sub-schedule-block cat-{s_cat}" style="top: {sub_top_rel}px; height: {sub_height}px;">'
                    html_content += f'<a href="{s_href}" target="_self">'
                    html_content += f'<strong>{s_time_str}</strong> {sub_row["サブスケジュールタイトル"]}'
                    html_content += '</a>'
                    html_content += '</div>'
            
            html_content += '</div>'

    occupied_intervals.sort()
    merged = []
    if occupied_intervals:
        c_start, c_end = occupied_intervals[0]
        for s, e in occupied_intervals[1:]:
            if s <= c_end:
                c_end = max(c_end, e)
            else:
                merged.append((c_start, c_end))
                c_start, c_end = s, e
        merged.append((c_start, c_end))
        
        last_end = get_adjusted_top(0)
        day_end_pos = get_adjusted_top(1440)
        
        for s, e in merged:
            if s - last_end >= 60: 
                empty_px = s - last_end
                empty_min = empty_px // 2
                html_content += f'<div class="empty-slot" style="top: {last_end}px; height: {empty_px}px;">空き時間 ({empty_min}分)</div>'
            last_end = e
        if day_end_pos - last_end >= 60:
            empty_px = day_end_pos - last_end
            empty_min = empty_px // 2
            html_content += f'<div class="empty-slot" style="top: {last_end}px; height: {empty_px}px;">空き時間 ({empty_min}分)</div>'
    else:
        total_px = get_adjusted_top(1440) - get_adjusted_top(0)
        html_content += f'<div class="empty-slot" style="top: 0px; height: {total_px}px;">空き時間 (24時間)</div>'

    html_content += '</div>'
    st.markdown(html_content, unsafe_allow_html=True)
    
    scroll_target = st.session_state.get('scroll_target')
    if scroll_target:
        st.markdown(f"""
            <script>
                setTimeout(function() {{
                    const el = document.getElementById("{scroll_target}");
                    if (el) {{
                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        el.style.transition = "background-color 0.5s";
                        let originalBg = el.style.backgroundColor;
                        el.style.backgroundColor = "#fff9c4";
                        setTimeout(() => {{ el.style.backgroundColor = originalBg; }}, 1000);
                    }}
                }}, 300);
            </script>
        """, unsafe_allow_html=True)
        st.session_state.scroll_target = None

    st.write("") 
    col_prev2, col_next2 = st.columns(2)
    with col_prev2:
        if has_prev and st.button(f"← {prev_date.strftime('%m/%d')} に移動", key="prev_bottom", use_container_width=True):
            st.session_state.selected_date = prev_date
            st.rerun()
    with col_next2:
        if has_next and st.button(f"{next_date.strftime('%m/%d')} に移動 →", key="next_bottom", use_container_width=True):
            st.session_state.selected_date = next_date
            st.rerun()

def render_schedule_detail():
    st.title("スケジュール詳細")
    
    detail_id = st.session_state.get('detail_id')
    detail_type = st.session_state.get('detail_type')
    travel_id = st.session_state.get('detail_travel_id') or st.session_state.get('selected_travel_id')
    parent_sched = st.session_state.get('detail_parent_sched')
    
    if not detail_id:
        st.error("詳細情報が見つかりません。")
        if st.button("← タイムラインへ戻る"):
            navigate_to('timeline')
        return
        
    try:
        if detail_type == 'main':
            df = load_data('Schedule')
            cond = (df['スケジュールナンバー'] == int(detail_id))
            if travel_id is not None and 'トラベルナンバー' in df.columns:
                cond &= (df['トラベルナンバー'] == int(travel_id))
            row = df[cond].iloc[0]
            title = row.get('スケジュールタイトル', 'タイトルなし')
            start = row.get('スケジュール開始時間', '')
            end = row.get('スケジュール終了時間', '')
            cat = row.get('スケジュール分類', 'その他')
        else:
            df = load_data('Sub_Schedule')
            if 'サブスケジュールナンバー' in df.columns:
                cond = (df['サブスケジュールナンバー'] == int(detail_id))
                if travel_id is not None and 'トラベルナンバー' in df.columns:
                    cond &= (df['トラベルナンバー'] == int(travel_id))
                if parent_sched is not None and 'スケジュールナンバー' in df.columns:
                    cond &= (df['スケジュールナンバー'] == int(parent_sched))
                row = df[cond].iloc[0]
            else:
                row = df.iloc[int(detail_id)]
            title = row.get('サブスケジュールタイトル', 'タイトルなし')
            start = row.get('サブスケジュール開始時間', '')
            end = row.get('サブスケジュール終了時間', '')
            cat = row.get('スケジュール分類', 'その他')

        travel_num = row.get('トラベルナンバー')
        if pd.notna(travel_num):
            st.session_state.selected_travel_id = int(travel_num)
        
        if pd.notna(start):
            st.session_state.selected_date = pd.to_datetime(start).date()

        st.session_state.current_travel_num = travel_num
        st.session_state.current_sched_num = row.get('スケジュールナンバー')

        # 共有モード時は編集・金額登録・サブ登録などのボタンを非表示
        if st.session_state.is_shared_view:
            if st.button("← タイムラインへ戻る", use_container_width=True):
                st.session_state.detail_id = None
                prefix = "sched" if detail_type == 'main' else "sub"
                st.session_state.scroll_target = f"{prefix}_{detail_id}"
                navigate_to('timeline')
        else:
            if detail_type == 'main':
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                with col_b1:
                    if st.button("← 戻る", use_container_width=True):
                        st.session_state.detail_id = None
                        navigate_to('timeline')
                with col_b2:
                    if st.button("編集", use_container_width=True):
                        navigate_to('edit_schedule')
                with col_b3:
                    if st.button("金額登録", use_container_width=True):
                        navigate_to('register_money')
                with col_b4:
                    if st.button("サブ登録", use_container_width=True, type="primary"):
                        navigate_to('create_sub_schedule')
            else:
                col_back, col_edit, col_money = st.columns(3)
                with col_back:
                    if st.button("← タイムラインへ戻る", use_container_width=True):
                        st.session_state.detail_id = None
                        prefix = "sched" if detail_type == 'main' else "sub"
                        st.session_state.scroll_target = f"{prefix}_{detail_id}"
                        navigate_to('timeline')
                with col_edit:
                    if st.button("編集", use_container_width=True):
                        navigate_to('edit_schedule')
                with col_money:
                    if st.button("金額を登録", use_container_width=True):
                        navigate_to('register_money')

        summary = row.get('概要', '（登録されていません）')
        raw_url = str(row.get('URL', ''))
        url = raw_url.strip('"') if raw_url else ''
        dep_lat = row.get('出発地緯度', '')
        dep_lon = row.get('出発地経度', '')
        arr_lat = row.get('到着地緯度', '')
        arr_lon = row.get('到着地経度', '')
        
        st.subheader(title)
        st.write(f"**時間:** {start} 〜 {end}")
        st.write(f"**分類:** {cat}")
        
        st.markdown("### 概要")
        st.write(summary)
        
        if pd.notna(url) and str(url).strip():
            st.markdown("### URL")
            st.write(url)
            
        st.markdown("### 場所")
        if cat != '移動':
            if pd.notna(dep_lat) and pd.notna(dep_lon) and str(dep_lat).strip() and str(dep_lon).strip():
                try:
                    df_map = pd.DataFrame({'lat': [float(dep_lat)], 'lon': [float(dep_lon)], 'color': ['#FF0000']})
                    st.map(df_map, color='color')
                except ValueError:
                    st.write("緯度・経度のデータが正しくありません。")
            else:
                st.write("位置情報が登録されていません。")
        else:
            coords = []
            colors = []
            if pd.notna(dep_lat) and pd.notna(dep_lon) and str(dep_lat).strip() and str(dep_lon).strip():
                try:
                    coords.append({'lat': float(dep_lat), 'lon': float(dep_lon)})
                    colors.append('#0000FF') 
                except ValueError:
                    pass
            if pd.notna(arr_lat) and pd.notna(arr_lon) and str(arr_lat).strip() and str(arr_lon).strip():
                try:
                    coords.append({'lat': float(arr_lat), 'lon': float(arr_lon)})
                    colors.append('#FF0000') 
                except ValueError:
                    pass
                    
            if coords:
                df_map = pd.DataFrame(coords)
                df_map['color'] = colors
                st.map(df_map, color='color')
                st.caption("※青色のピンが出発地、赤色のピンが到着地を示しています。")
            else:
                st.write("位置情報が登録されていません。")

        df_money = load_data('Money')
        df_member = load_data('Member')
        
        if not df_money.empty:
            sched_num = row.get('スケジュールナンバー')
            
            if detail_type == 'main':
                cond = (df_money['トラベルナンバー'] == int(travel_num)) & \
                       (df_money['スケジュールナンバー'] == int(sched_num)) & \
                       (df_money['サブスケジュールナンバー'].isna() | (df_money['サブスケジュールナンバー'] == ''))
            else:
                cond = (df_money['トラベルナンバー'] == int(travel_num)) & \
                       (df_money['スケジュールナンバー'] == int(sched_num)) & \
                       (df_money['サブスケジュールナンバー'] == int(detail_id))
            
            df_target_money = df_money[cond].copy()
            
            if not df_target_money.empty:
                df_target_money['金額'] = pd.to_numeric(df_target_money['金額'], errors='coerce').fillna(0)
                total_amount = df_target_money['金額'].sum()
                
                if total_amount > 0:
                    st.markdown("### 費用")
                    st.write(f"**合計金額:** {total_amount:,.0f}円")
                    st.write("**支払者内訳:**")
                    
                    breakdown = df_target_money.groupby('メンバーナンバー')['金額'].sum()
                    
                    for member_num, amount in breakdown.items():
                        member_name = member_num 
                        
                        if not df_member.empty and 'トラベルナンバー' in df_member.columns and 'メンバーナンバー' in df_member.columns and '名前' in df_member.columns:
                            matched_member = df_member[
                                (df_member['トラベルナンバー'] == int(travel_num)) & 
                                (df_member['メンバーナンバー'] == member_num)
                            ]
                            if not matched_member.empty:
                                member_name = matched_member.iloc[0]['名前']
                                
                        st.write(f"{member_name} {amount:,.0f}円")
        
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")
        if st.button("← タイムラインへ戻る"):
            navigate_to('timeline')

def render_edit_schedule():
    if st.session_state.is_shared_view:
        st.error("権限がありません。")
        return
    st.title("スケジュール編集")
    
    if st.button("登録せずに戻る"):
        navigate_to('schedule_detail')
        
    detail_id = st.session_state.get('detail_id')
    detail_type = st.session_state.get('detail_type')
    travel_id = st.session_state.get('detail_travel_id') or st.session_state.get('selected_travel_id')
    parent_sched = st.session_state.get('detail_parent_sched')
    
    try:
        if detail_type == 'main':
            df = load_data('Schedule')
            cond = (df['スケジュールナンバー'] == int(detail_id))
            if travel_id is not None and 'トラベルナンバー' in df.columns:
                cond &= (df['トラベルナンバー'] == int(travel_id))
            row = df[cond].iloc[0]
            is_sub = False
        else:
            df = load_data('Sub_Schedule')
            cond = (df['サブスケジュールナンバー'] == int(detail_id))
            if travel_id is not None and 'トラベルナンバー' in df.columns:
                cond &= (df['トラベルナンバー'] == int(travel_id))
            if parent_sched is not None and 'スケジュールナンバー' in df.columns:
                cond &= (df['スケジュールナンバー'] == int(parent_sched))
            row = df[cond].iloc[0]
            is_sub = True

        with st.form("edit_form"):
            title_label = "スケジュールタイトル" if not is_sub else "サブスケジュールタイトル"
            title_key = "スケジュールタイトル" if not is_sub else "サブスケジュールタイトル"
            
            title = st.text_input(title_label, value=str(row.get(title_key, '')))
            
            cats = ['移動', '活動', '食事', '宿泊', 'その他']
            current_cat = row.get('スケジュール分類', 'その他')
            cat_idx = cats.index(current_cat) if current_cat in cats else 4
            cat = st.selectbox("分類", cats, index=cat_idx)
            
            start_col = "スケジュール開始時間" if not is_sub else "サブスケジュール開始時間"
            end_col = "スケジュール終了時間" if not is_sub else "サブスケジュール終了時間"
            
            start_val = pd.to_datetime(row.get(start_col, pd.Timestamp.now()))
            end_val = pd.to_datetime(row.get(end_col, pd.Timestamp.now()))
            
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                start_date = st.date_input("開始日", value=start_val.date())
                c_h1, c_m1 = st.columns(2)
                with c_h1:
                    start_h = st.selectbox("開始時", list(range(24)), index=start_val.hour, key="edit_start_h")
                with c_m1:
                    start_m = st.selectbox("開始分", list(range(60)), index=start_val.minute, key="edit_start_m")
                start_time = pd.Timestamp(f"{start_h:02d}:{start_m:02d}:00").time()
            with col_s2:
                end_date = st.date_input("終了日", value=end_val.date())
                c_h2, c_m2 = st.columns(2)
                with c_h2:
                    end_h = st.selectbox("終了時", list(range(24)), index=end_val.hour, key="edit_end_h")
                with c_m2:
                    end_m = st.selectbox("終了分", list(range(60)), index=end_val.minute, key="edit_end_m")
                end_time = pd.Timestamp(f"{end_h:02d}:{end_m:02d}:00").time()
                
            summary = st.text_area("概要", value=str(row.get('概要', '')))
            raw_edit_url = str(row.get('URL', ''))
            edit_url_val = raw_edit_url.strip('"') if raw_edit_url else ''
            url = st.text_input("URL", value=edit_url_val)
            
            dep_lat = row.get('出発地緯度', '')
            dep_lon = row.get('出発地経度', '')
            arr_lat = row.get('到着地緯度', '')
            arr_lon = row.get('到着地経度', '')
            
            if cat == '移動':
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    new_dep_lat = st.text_input("出発地緯度", value=str(dep_lat))
                    new_dep_lon = st.text_input("出発地経度", value=str(dep_lon))
                with col_d2:
                    new_arr_lat = st.text_input("到着地緯度", value=str(arr_lat))
                    new_arr_lon = st.text_input("到着地経度", value=str(arr_lon))
            else:
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    new_dep_lat = st.text_input("出発地緯度 (場所)", value=str(dep_lat))
                with col_d2:
                    new_dep_lon = st.text_input("出発地経度 (場所)", value=str(dep_lon))
                new_arr_lat, new_arr_lon = '', ''

            submitted = st.form_submit_button("登録", use_container_width=True)
            
        if submitted:
            client = get_gspread_client()
            sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
            sheet_name = "Schedule" if not is_sub else "Sub_Schedule"
            worksheet = sh.worksheet(sheet_name)
            
            start_str = f"{start_date.strftime('%Y/%m/%d')} {start_time.strftime('%H:%M:%S')}"
            end_str = f"{end_date.strftime('%Y/%m/%d')} {end_time.strftime('%H:%M:%S')}"
            
            clean_url = url.strip()
            formatted_url = f'"{clean_url}"' if clean_url else ""
            
            header = worksheet.row_values(1)
            def get_col_idx(col_name):
                try:
                    return header.index(col_name) + 1
                except ValueError:
                    return None

            records = worksheet.get_all_records()
            target_row_idx = None
            
            for idx, rec in enumerate(records):
                t_match = str(rec.get('トラベルナンバー')) == str(travel_id)
                if not is_sub:
                    s_match = str(rec.get('スケジュールナンバー')) == str(detail_id)
                    if t_match and s_match:
                        target_row_idx = idx + 2
                        break
                else:
                    sub_match = str(rec.get('サブスケジュールナンバー')) == str(detail_id)
                    sched_match = str(rec.get('スケジュールナンバー')) == str(parent_sched)
                    if t_match and sched_match and sub_match:
                        target_row_idx = idx + 2
                        break
                        
            if target_row_idx:
                title_col_name = "スケジュールタイトル" if not is_sub else "サブスケジュールタイトル"
                start_col_name = "スケジュール開始時間" if not is_sub else "サブスケジュール開始時間"
                end_col_name = "スケジュール終了時間" if not is_sub else "サブスケジュール終了時間"
                
                update_data = {
                    title_col_name: title,
                    start_col_name: start_str,
                    end_col_name: end_str,
                    "スケジュール分類": cat,
                    "出発地緯度": new_dep_lat,
                    "出発地経度": new_dep_lon,
                    "到着地緯度": new_arr_lat,
                    "到着地経度": new_arr_lon,
                    "URL": formatted_url,
                    "概要": summary
                }
                
                for col_name, val in update_data.items():
                    col_idx = get_col_idx(col_name)
                    if col_idx:
                        worksheet.update_cell(target_row_idx, col_idx, val)
                
                st.success("スケジュールを更新しました！")
                clear_cache()
                navigate_to('schedule_detail')
            else:
                st.error("スプレッドシート内で該当する行が見つかりませんでした。")
            
    except Exception as e:
        st.error(f"データの処理に失敗しました: {e}")

def render_register_money():
    if st.session_state.is_shared_view:
        st.error("権限がありません。")
        return
    st.title("金額登録")
    
    if st.button("← 詳細へ戻る"):
        navigate_to('schedule_detail')
        
    travel_id = st.session_state.get('selected_travel_id')
    detail_id = st.session_state.get('detail_id')
    detail_type = st.session_state.get('detail_type')
    sched_num = st.session_state.get('current_sched_num')
    
    df_member = load_data('Member')
    travel_members = []
    if not df_member.empty and 'トラベルナンバー' in df_member.columns:
        travel_members = df_member[df_member['トラベルナンバー'] == travel_id].to_dict('records')
        
    if not travel_members:
        st.info("この旅行に登録されているメンバーがいません。Memberシートを確認してください。")
        return
        
    df_money = load_data('Money')
    existing_amounts = {}
    if not df_money.empty and 'トラベルナンバー' in df_money.columns:
        df_money['トラベルナンバー'] = pd.to_numeric(df_money['トラベルナンバー'], errors='coerce')
        df_money['スケジュールナンバー'] = pd.to_numeric(df_money['スケジュールナンバー'], errors='coerce')
        if 'サブスケジュールナンバー' in df_money.columns:
            df_money['サブスケジュールナンバー'] = pd.to_numeric(df_money['サブスケジュールナンバー'], errors='coerce')
            
        if detail_type == 'main':
            cond = (df_money['トラベルナンバー'] == int(travel_id)) & \
                   (df_money['スケジュールナンバー'] == int(sched_num)) & \
                   (df_money['サブスケジュールナンバー'].isna() | (df_money['サブスケジュールナンバー'].astype(str).str.strip() == ''))
        else:
            cond = (df_money['トラベルナンバー'] == int(travel_id)) & \
                   (df_money['スケジュールナンバー'] == int(sched_num)) & \
                   (df_money['サブスケジュールナンバー'] == int(detail_id))
                   
        matched_money = df_money[cond]
        for _, m_row in matched_money.iterrows():
            m_num = int(m_row['メンバーナンバー'])
            amt = float(m_row['金額']) if pd.notna(m_row['金額']) else 0
            existing_amounts[m_num] = amt

    st.write("各メンバーの支払金額を入力してください。")
    
    with st.form("money_form"):
        amounts = {}
        for m in travel_members:
            m_num = m.get('メンバーナンバー')
            m_name = m.get('名前', f"メンバー {m_num}")
            default_val = int(existing_amounts.get(int(m_num), 0))
            amounts[m_num] = st.number_input(f"{m_name} の支払金額 (円)", min_value=0, value=default_val, step=100)
            
        submitted = st.form_submit_button("金額を登録", use_container_width=True)
        
    if submitted:
        try:
            client = get_gspread_client()
            sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
            worksheet = sh.worksheet("Money")
            
            records = worksheet.get_all_records()
            rows_to_delete = []
            
            for idx, rec in enumerate(records):
                t_match = str(rec.get('トラベルナンバー')) == str(travel_id)
                s_match = str(rec.get('スケジュールナンバー')) == str(sched_num)
                
                if detail_type == 'main':
                    sub_val = str(rec.get('サブスケジュールナンバー', '')).strip()
                    sub_match = (sub_val == '' or sub_val == 'nan')
                else:
                    sub_val = str(rec.get('サブスケジュールナンバー', '')).strip()
                    sub_match = (sub_val == str(detail_id))
                    
                if t_match and s_match and sub_match:
                    rows_to_delete.append(idx + 2) 
                    
            for r_idx in sorted(rows_to_delete, reverse=True):
                worksheet.delete_rows(r_idx)
                
            for m_num, amount in amounts.items():
                if amount > 0:
                    if detail_type == 'main':
                        worksheet.append_row([
                            int(travel_id),
                            int(sched_num),
                            "",
                            int(m_num),
                            float(amount)
                        ])
                    else:
                        worksheet.append_row([
                            int(travel_id),
                            int(sched_num),
                            int(detail_id),
                            int(m_num),
                            float(amount)
                        ])
                        
            st.success("金額を登録しました！")
            clear_cache()
            navigate_to('schedule_detail')
        except Exception as e:
            st.error(f"金額の保存に失敗しました: {e}")

def render_create_schedule():
    if st.session_state.is_shared_view:
        st.error("権限がありません。")
        return
    st.title("スケジュール新規登録")
    
    if st.button("登録せずに戻る"):
        navigate_to('timeline')
        
    travel_id = st.session_state.get('selected_travel_id')
    default_date = st.session_state.get('selected_date') or pd.Timestamp.now().date()
    
    cats = ['移動', '活動', '食事', '宿泊', 'その他']
    cat = st.selectbox("分類", cats, index=1) 
    
    with st.form("create_form"):
        title = st.text_input("スケジュールタイトル")
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            start_date = st.date_input("開始日", value=default_date)
            c_h1, c_m1 = st.columns(2)
            with c_h1:
                start_h = st.selectbox("開始時", list(range(24)), index=9, key="create_start_h")
            with c_m1:
                start_m = st.selectbox("開始分", list(range(60)), index=0, key="create_start_m")
            start_time = pd.Timestamp(f"{start_h:02d}:{start_m:02d}:00").time()
        with col_s2:
            end_date = st.date_input("終了日", value=default_date)
            c_h2, c_m2 = st.columns(2)
            with c_h2:
                end_h = st.selectbox("終了時", list(range(24)), index=10, key="create_end_h")
            with c_m2:
                end_m = st.selectbox("終了分", list(range(60)), index=0, key="create_end_m")
            end_time = pd.Timestamp(f"{end_h:02d}:{end_m:02d}:00").time()
            
        summary = st.text_area("概要", value="")
        url = st.text_input("URL", value="")
        
        if cat == '移動':
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dep_lat = st.text_input("出発地緯度", value="")
                dep_lon = st.text_input("出発地経度", value="")
            with col_d2:
                arr_lat = st.text_input("到着地緯度", value="")
                arr_lon = st.text_input("到着地経度", value="")
        else:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dep_lat = st.text_input("出発地緯度 (場所)", value="")
            with col_d2:
                dep_lon = st.text_input("出発地経度 (場所)", value="")
            arr_lat, arr_lon = '', ''

        submitted = st.form_submit_button("登録", use_container_width=True)
        
    if submitted:
        if not title.strip():
            st.error("タイトルを入力してください。")
            return

        new_start_dt = pd.to_datetime(f"{start_date.strftime('%Y/%m/%d')} {start_time.strftime('%H:%M:%S')}")
        new_end_dt = pd.to_datetime(f"{end_date.strftime('%Y/%m/%d')} {end_time.strftime('%H:%M:%S')}")

        if new_end_dt <= new_start_dt:
            st.error("終了時間は開始時間より後の時間を設定してください。")
            return

        df_sched = load_data('Schedule')
        if not df_sched.empty and 'トラベルナンバー' in df_sched.columns:
            target_scheds = df_sched[df_sched['トラベルナンバー'] == int(travel_id)]
            
            for _, r in target_scheds.iterrows():
                try:
                    ex_start = pd.to_datetime(r['スケジュール開始時間'])
                    ex_end = pd.to_datetime(r['スケジュール終了時間'])
                    ex_title = r.get('スケジュールタイトル', '名称不明')
                    
                    if new_start_dt < ex_end and new_end_dt > ex_start:
                        ex_s_str = ex_start.strftime("%H:%M")
                        ex_e_str = ex_end.strftime("%H:%M")
                        st.error(f"{ex_s_str}から{ex_e_str}まで「{ex_title}」というスケジュールが入っています")
                        return
                except Exception:
                    continue

        new_sched_num = 1
        if not df_sched.empty and 'トラベルナンバー' in df_sched.columns and 'スケジュールナンバー' in df_sched.columns:
            target_scheds = df_sched[df_sched['トラベルナンバー'] == int(travel_id)]
            if not target_scheds.empty:
                s_nums = pd.to_numeric(target_scheds['スケジュールナンバー'], errors='coerce').dropna()
                if not s_nums.empty:
                    new_sched_num = int(s_nums.max()) + 1

        try:
            client = get_gspread_client()
            sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
            worksheet = sh.worksheet("Schedule")
            
            clean_url = url.strip()
            formatted_url = f'"{clean_url}"' if clean_url else ""
            
            start_str = new_start_dt.strftime('%Y/%m/%d %H:%M:%S')
            end_str = new_end_dt.strftime('%Y/%m/%d %H:%M:%S')
            
            new_row = [
                int(travel_id),
                int(new_sched_num),
                title,
                start_str,
                end_str,
                cat,
                dep_lat,
                dep_lon,
                arr_lat if cat == '移動' else '',
                arr_lon if cat == '移動' else '',
                formatted_url,
                summary
            ]
            
            worksheet.append_row(new_row)
            st.success(f"「{title}」を登録しました！")
            clear_cache()
            
            st.session_state.selected_date = start_date
            navigate_to('timeline')
            
        except Exception as e:
            st.error(f"保存に失敗しました: {e}")

def render_create_sub_schedule():
    if st.session_state.is_shared_view:
        st.error("権限がありません。")
        return
    st.title("サブスケジュール新規登録")
    
    if st.button("登録せずに戻る"):
        navigate_to('schedule_detail')
        
    travel_id = st.session_state.get('selected_travel_id')
    parent_sched_num = st.session_state.get('current_sched_num')
    default_date = st.session_state.get('selected_date') or pd.Timestamp.now().date()
    
    cats = ['移動', '活動', '食事', '宿泊', 'その他']
    cat = st.selectbox("分類", cats, index=1)
    
    with st.form("create_sub_form"):
        title = st.text_input("サブスケジュールタイトル")
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            start_date = st.date_input("開始日", value=default_date)
            c_h1, c_m1 = st.columns(2)
            with c_h1:
                start_h = st.selectbox("開始時", list(range(24)), index=9, key="sub_start_h")
            with c_m1:
                start_m = st.selectbox("開始分", list(range(60)), index=0, key="sub_start_m")
            start_time = pd.Timestamp(f"{start_h:02d}:{start_m:02d}:00").time()
        with col_s2:
            end_date = st.date_input("終了日", value=default_date)
            c_h2, c_m2 = st.columns(2)
            with c_h2:
                end_h = st.selectbox("終了時", list(range(24)), index=10, key="sub_end_h")
            with c_m2:
                end_m = st.selectbox("終了分", list(range(60)), index=0, key="sub_end_m")
            end_time = pd.Timestamp(f"{end_h:02d}:{end_m:02d}:00").time()
            
        summary = st.text_area("概要", value="")
        url = st.text_input("URL", value="")
        
        if cat == '移動':
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dep_lat = st.text_input("出発地緯度", value="")
                dep_lon = st.text_input("出発地経度", value="")
            with col_d2:
                arr_lat = st.text_input("到着地緯度", value="")
                arr_lon = st.text_input("到着地経度", value="")
        else:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dep_lat = st.text_input("出発地緯度 (場所)", value="")
            with col_d2:
                dep_lon = st.text_input("出発地経度 (場所)", value="")
            arr_lat, arr_lon = '', ''

        submitted = st.form_submit_button("登録", use_container_width=True)
        
    if submitted:
        if not title.strip():
            st.error("タイトルを入力してください。")
            return

        new_start_dt = pd.to_datetime(f"{start_date.strftime('%Y/%m/%d')} {start_time.strftime('%H:%M:%S')}")
        new_end_dt = pd.to_datetime(f"{end_date.strftime('%Y/%m/%d')} {end_time.strftime('%H:%M:%S')}")

        if new_end_dt <= new_start_dt:
            st.error("終了時間は開始時間より後の時間を設定してください。")
            return

        df_sub = load_data('Sub_Schedule')
        if not df_sub.empty and 'トラベルナンバー' in df_sub.columns and 'スケジュールナンバー' in df_sub.columns:
            target_subs = df_sub[
                (df_sub['トラベルナンバー'] == int(travel_id)) & 
                (df_sub['スケジュールナンバー'] == int(parent_sched_num))
            ]
            
            for _, r in target_subs.iterrows():
                try:
                    ex_start = pd.to_datetime(r['サブスケジュール開始時間'])
                    ex_end = pd.to_datetime(r['サブスケジュール終了時間'])
                    ex_title = r.get('サブスケジュールタイトル', '名称不明')
                    
                    if new_start_dt < ex_end and new_end_dt > ex_start:
                        ex_s_str = ex_start.strftime("%H:%M")
                        ex_e_str = ex_end.strftime("%H:%M")
                        st.error(f"{ex_s_str}から{ex_e_str}まで「{ex_title}」というサブスケジュールが入っています")
                        return
                except Exception:
                    continue

        new_sub_num = 1
        if not df_sub.empty and 'トラベルナンバー' in df_sub.columns and 'スケジュールナンバー' in df_sub.columns and 'サブスケジュールナンバー' in df_sub.columns:
            target_subs = df_sub[
                (df_sub['トラベルナンバー'] == int(travel_id)) & 
                (df_sub['スケジュールナンバー'] == int(parent_sched_num))
            ]
            if not target_subs.empty:
                sub_nums = pd.to_numeric(target_subs['サブスケジュールナンバー'], errors='coerce').dropna()
                if not sub_nums.empty:
                    new_sub_num = int(sub_nums.max()) + 1

        try:
            client = get_gspread_client()
            sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
            worksheet = sh.worksheet("Sub_Schedule")
            
            clean_url = url.strip()
            formatted_url = f'"{clean_url}"' if clean_url else ""
            
            start_str = new_start_dt.strftime('%Y/%m/%d %H:%M:%S')
            end_str = new_end_dt.strftime('%Y/%m/%d %H:%M:%S')
            
            raw_header = worksheet.row_values(1)
            header = [str(h).strip() for h in raw_header]
            def get_col_idx(col_name):
                try:
                    return header.index(str(col_name).strip()) + 1
                except ValueError:
                    return None

            next_row_idx = len(worksheet.get_all_values()) + 1
            
            insert_data = {
                "トラベルナンバー": int(travel_id),
                "スケジュールナンバー": int(parent_sched_num),
                "サブスケジュールナンバー": int(new_sub_num),
                "サブスケジュールタイトル": title,
                "サブスケジュール開始時間": start_str,
                "サブスケジュール終了時間": end_str,
                "スケジュール分類": cat,
                "出発地緯度": dep_lat,
                "出発地経度": dep_lon,
                "到着地緯度": arr_lat if cat == '移動' else '',
                "到着地経度": arr_lon if cat == '移動' else '',
                "URL": formatted_url,
                "概要": summary
            }
            
            worksheet.append_row([]) 
            
            for col_name, val in insert_data.items():
                col_idx = get_col_idx(col_name)
                if col_idx:
                    worksheet.update_cell(next_row_idx, col_idx, val)
            
            st.success(f"「{title}」を登録しました！")
            clear_cache()
            
            st.session_state.selected_date = start_date
            navigate_to('schedule_detail')
            
        except Exception as e:
            st.error(f"保存に失敗しました: {e}")

def render_register_member():
    if st.session_state.is_shared_view:
        st.error("権限がありません。")
        return
    st.title("メンバー登録")
    
    if st.button("← 日一覧へ戻る"):
        navigate_to('day_list')
        
    travel_id = st.session_state.get('selected_travel_id')
    df_member = load_data('Member')
    
    existing_members = []
    if not df_member.empty and 'トラベルナンバー' in df_member.columns:
        matched = df_member[df_member['トラベルナンバー'] == travel_id]
        if not matched.empty:
            if 'メンバーナンバー' in matched.columns:
                matched = matched.sort_values('メンバーナンバー')
            existing_members = matched['名前'].tolist()
            
    if 'member_input_count' not in st.session_state or st.session_state.get('current_member_travel_id') != travel_id:
        st.session_state.current_member_travel_id = travel_id
        st.session_state.member_input_count = max(len(existing_members) + 1, 1)

    with st.form("member_form"):
        st.write("旅行に参加するメンバーの名前を入力してください。")
        
        names = []
        for i in range(st.session_state.member_input_count):
            default_val = existing_members[i] if i < len(existing_members) else ""
            name = st.text_input(f"メンバー {i + 1}", value=default_val, key=f"member_name_{i}")
            names.append(name)
            
        submitted = st.form_submit_button("登録を保存", use_container_width=True)
        
    if st.button("＋ 入力欄を追加"):
        st.session_state.member_input_count += 1
        st.rerun()

    if submitted:
        try:
            client = get_gspread_client()
            sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
            worksheet = sh.worksheet("Member")
            
            records = worksheet.get_all_records()
            rows_to_delete = []
            for idx, rec in enumerate(records):
                if str(rec.get('トラベルナンバー')) == str(travel_id):
                    rows_to_delete.append(idx + 2)
                    
            for r_idx in sorted(rows_to_delete, reverse=True):
                worksheet.delete_rows(r_idx)
                
            valid_num = 1
            for name in names:
                clean_name = name.strip()
                if clean_name:
                    worksheet.append_row([
                        int(travel_id),
                        int(valid_num),
                        clean_name
                    ])
                    valid_num += 1
                    
            st.success("メンバーを登録しました！")
            clear_cache()
            navigate_to('day_list')
        except Exception as e:
            st.error(f"メンバーの保存に失敗しました: {e}")

# ==========================================
# メインルーティング (画面の振り分け)
# ==========================================
if __name__ == "__main__":
    import streamlit.runtime
    if not streamlit.runtime.exists():
        script_path = os.path.abspath(__file__)
        print("Streamlitサーバーを自動起動しています...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", script_path])
        sys.exit(0)

params = dict(st.query_params)

view_travel = params.get("view_travel")
if view_travel:
    try:
        st.session_state.is_shared_view = True
        st.session_state.selected_travel_id = int(view_travel)
    except (TypeError, ValueError):
        pass

if params.get("detail_id"):
    try:
        st.session_state.detail_id = params.get("detail_id")
        st.session_state.detail_type = params.get("type", "main")
        st.session_state.detail_travel_id = params.get("travel_id") or view_travel
        st.session_state.detail_parent_sched = params.get("parent_sched")
        st.session_state.current_page = "schedule_detail"
    except Exception:
        pass
elif view_travel:
    st.session_state.current_page = "day_list"

st.query_params.clear()

if st.session_state.current_page == 'start':
    render_start()
elif st.session_state.current_page == 'register_travel':
    render_register_travel()
elif st.session_state.current_page == 'year_list':
    render_year_list()
elif st.session_state.current_page == 'travel_list':
    render_travel_list()
elif st.session_state.current_page == 'day_list':
    render_day_list()
elif st.session_state.current_page == 'timeline':
    render_timeline()
elif st.session_state.current_page == 'schedule_detail':
    render_schedule_detail()
elif st.session_state.current_page == 'edit_schedule':
    render_edit_schedule()
elif st.session_state.current_page == 'create_schedule':
    render_create_schedule()
elif st.session_state.current_page == 'create_sub_schedule':
    render_create_sub_schedule()
elif st.session_state.current_page == 'register_money':
    render_register_money()
elif st.session_state.current_page == 'register_member':
    render_register_member()