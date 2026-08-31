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
st.set_page_config(page_title="Travel App (View Only)", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .block-container {
        max-width: 100% !important;
        padding-left: 1vw !important;
        padding-right: 1vw !important;
    }
    html, body, [class*="css"], .stMarkdown, .stText, p, span, div, label, input, button {
        font-size: 4vw !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# スプレッドシート連携関数
# ==========================================
@st.cache_resource
def get_gspread_client():
    """スプレッドシートAPIクライアントを初期化してキャッシュする"""
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=600)
def load_data(sheet_name):
    """指定したシート名のデータをDataFrameとして読み込む"""
    try:
        client = get_gspread_client()
        sh = client.open_by_key(st.secrets["spreadsheet"]["spreadsheet_id"])
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")
        return pd.DataFrame()

# ==========================================
# 状態管理 (Session State)
# ==========================================
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'start'

if 'selected_year' not in st.session_state:
    st.session_state.selected_year = None
if 'selected_travel_id' not in st.session_state:
    st.session_state.selected_travel_id = None
if 'selected_date' not in st.session_state:
    st.session_state.selected_date = None

def navigate_to(page_name):
    """画面遷移用関数"""
    st.session_state.current_page = page_name
    st.rerun()

# ==========================================
# 画面ごとの描画関数 (閲覧・参照専用)
# ==========================================

def render_day_list():
    travel_id = st.session_state.selected_travel_id
    df_travel = load_data('Travel')
    
    if df_travel.empty or travel_id not in df_travel['トラベルナンバー'].values:
        st.error("旅行データが見つかりません。")
        return
        
    travel_row = df_travel[df_travel['トラベルナンバー'] == travel_id].iloc[0]
    st.title(f"{travel_row['タイトル']} - 日一覧")
            
    # --- 旅行全体の金額集計処理 ---
    df_money = load_data('Money')
    df_sched = load_data('Schedule')
    df_sub = load_data('Sub_Schedule')
    df_member = load_data('Member')
    
    total_travel_money = 0
    daily_summary = {}   
    member_summary = {}  
    cat_summary = {      
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
            extra_vw = delta_h * 0.5
            
            if extra_vw > 0:
                offset_list.append((e_min, extra_vw))

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
            extra_vw = delta_h * 0.1
            
            if extra_vw > 0:
                offset_list.append((e_min, extra_vw))

    offset_list.sort(key=lambda x: x[0])

    def get_adjusted_top(minute_val):
        base_top = minute_val * 0.5
        accumulated_offset = sum(vw for t, vw in offset_list if t <= minute_val)
        return base_top + accumulated_offset

    total_container_height = get_adjusted_top(1440)

    st.markdown(f"""
        <style>
        .timeline-container {{
            position: relative;
            height: {total_container_height}vw;
            background-color: #fcfcfc;
            width: 100%;
            border-left: 15vw solid #e9ecef;
            border-radius: 0.5vw;
            margin-top: 1vw;
            box-shadow: 0 0.2vw 0.5vw rgba(0,0,0,0.05);
        }}
        .time-label {{
            position: absolute;
            left: -12vw;
            font-size: 3vw;
            color: #6c757d;
        }}
        .time-grid-line {{
            position: absolute;
            left: 0;
            right: 0;
            height: 0.1vw;
            background-color: #e0e0e0;
        }}
        .schedule-block {{
            position: absolute;
            left: 0%;
            right: 0%;
            border-radius: 0.5vw;
            padding: 0.4vw 0.2vw;
            font-size: 4vw;
            box-shadow: 0 0.2vw 0.4vw rgba(0,0,0,0.15);
            word-break: break-all;
            white-space: normal;
            border-left: 1.2vw solid #444;
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
            left: 50%;
            right: 0%;
            border-radius: 0.4vw;
            padding: 0.2vw 0.6vw;
            font-size: 2.5vw;
            box-shadow: 0 0.1vw 0.3vw rgba(0,0,0,0.2);
            word-break: break-all;
            white-space: normal;
            border-left: 0.4vw solid #666;
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
            left: 0%;
            right: 2%;
            background-color: rgba(200, 200, 200, 0.15);
            border: 0.2vw dashed #bbb;
            border-radius: 0.5vw;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #888;
            font-size: 3vw;
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
        html_content += f'<div class="time-label" style="top: {top-0.8}vw;">{h}:00</div>'
        html_content += f'<div class="time-grid-line" style="top: {top}vw;"></div>'

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
            href = f"?detail_id={sched_id}&type=main&travel_id2={travel_id}"
            
            html_content += f'<div id="sched_{sched_id}" class="schedule-block cat-{cat}" style="top: {top}vw; height: {height}vw;">'
            html_content += f'<a href="{href}" target="_self">'
            html_content += f'<div style="font-weight:bold; margin-bottom:0.2vw;">{time_str}</div><div>{title}</div>'
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
                    s_href = f"?detail_id={sub_id}&type=sub&travel_id2={travel_id}&parent_sched={sched_id}"
                    
                    html_content += f'<div id="sub_{sub_id}" class="sub-schedule-block cat-{s_cat}" style="top: {sub_top_rel}vw; height: {sub_height}vw;">'
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
                empty_vw = s - last_end
                empty_min = int(empty_vw / 0.1)
                html_content += f'<div class="empty-slot" style="top: {last_end}vw; height: {empty_vw}vw;">空き時間 ({empty_min}分)</div>'
            last_end = e
        if day_end_pos - last_end >= 60:
            empty_vw = day_end_pos - last_end
            empty_min = int(empty_vw / 0.1)
            html_content += f'<div class="empty-slot" style="top: {last_end}vw; height: {empty_vw}vw;">空き時間 ({empty_min}分)</div>'
    else:
        total_vw = get_adjusted_top(1440) - get_adjusted_top(0)
        html_content += f'<div class="empty-slot" style="top: 0vw; height: {total_vw}vw;">空き時間 (24時間)</div>'

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
    st.title("スケジュール詳細 (閲覧専用)")
    
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

        # 編集ボタンを一切排除し、戻るボタンのみ配置
        if st.button("← タイムラインへ戻る", use_container_width=True):
            st.session_state.detail_id = None
            prefix = "sched" if detail_type == 'main' else "sub"
            st.session_state.scroll_target = f"{prefix}_{detail_id}"
            navigate_to('timeline')

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

if "travel_id" in st.query_params and "detail_id" not in st.query_params and st.session_state.get('selected_travel_id') is None:
    try:
        encoded_travel = st.query_params["travel_id"]
        st.session_state.selected_travel_id = int(int(encoded_travel, 16) / 333)
    except ValueError:
        st.session_state.selected_travel_id = None
    st.session_state.current_page = 'day_list'
    st.rerun()

if "detail_id" in st.query_params:
    st.session_state.detail_id = st.query_params["detail_id"]
    st.session_state.detail_type = st.query_params.get("type", "main")
    st.session_state.selected_travel_id = st.query_params.get("travel_id2", None)
    st.stop()
    st.session_state.current_page = 'schedule_detail'
    st.markdown("""
        <script>
        const fullUrl = window.location.href;
        const firstQ = fullUrl.indexOf('?');
        if (firstQ !== -1) {
            const secondQ = fullUrl.indexOf('?', firstQ + 1);
            if (secondQ !== -1) {
                const cleanUrl = fullUrl.substring(0, secondQ);
                window.history.replaceState({}, document.title, cleanUrl);
            }
        }
        </script>
    """, unsafe_allow_html=True)
    st.rerun()

if st.session_state.current_page == 'start':
    render_start()
elif st.session_state.current_page == 'day_list':
    render_day_list()
elif st.session_state.current_page == 'timeline':
    render_timeline()
elif st.session_state.current_page == 'schedule_detail':
    render_schedule_detail()
# 編集・新規登録・メンバー登録などの関数呼び出し（および対応するrender関数自体）を完全に削除しました
