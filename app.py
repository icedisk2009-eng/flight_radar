import streamlit as st
import pandas as pd
import requests
import pydeck as pdk

st.set_page_config(page_title="한반도 실시간 비행기 추적", layout="wide")

st.title("✈️ 한반도 상공 실시간 비행기 이상 탐지 웹앱")
st.write("OpenSky API 데이터에 Z-score 통계 기법을 적용하여 급강하 중인 비행기를 자동으로 감지합니다.")

# -----------------------------------------------------------
# 1. 사이드바 UI 및 OpenSky 인증 설정
# -----------------------------------------------------------
st.sidebar.header("⚙️ 컨트롤 타워")
st.sidebar.button("🔄 실시간 데이터 새로고침")

# 깃허브 공개 방지를 위해 Streamlit Secrets에서 계정 정보를 가져옴
# (설정이 안 되어 있으면 인증 없이 요청하지만, 차단될 확률이 높음)
try:
    OPENSKY_USER = st.secrets["OPENSKY_USER"]
    OPENSKY_PASS = st.secrets["OPENSKY_PASS"]
    auth = (OPENSKY_USER, OPENSKY_PASS)
    st.sidebar.success("✅ OpenSky API 계정 연동 완료 (안정적 수신 중)")
except KeyError:
    auth = None
    st.sidebar.warning("⚠️ OpenSky 계정 정보가 없습니다. (익명 요청 중 - 제한 발생 가능)")

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 이상 탐지(Anomaly Detection) 설정")

z_threshold = st.sidebar.slider(
    "급강하 감지 Z-score 기준값",
    min_value=-5.0,
    max_value=5.0,
    value=-3.0,
    step=0.1
)

# -----------------------------------------------------------
# 2. 데이터 수집 (OpenSky API)
# -----------------------------------------------------------
def get_flight_data():
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}
    try:
        # auth 매개변수에 계정 정보를 넣어 호출 제한을 대폭 늘림
        response = requests.get(url, params=params, auth=auth, timeout=10)
        
        if response.status_code == 429:
            st.error("🚨 API 호출 한도 초과(Rate Limit). 잠시 후 다시 시도하세요.")
            return []
            
        data = response.json()
        if data is not None and data.get("states") is not None:
            return data["states"]
        return []
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return []

raw_data = get_flight_data()

# -----------------------------------------------------------
# 3. 데이터 전처리 및 Z-score 계산
# -----------------------------------------------------------
if len(raw_data) > 0:
    columns = [
        'icao24', 'callsign', 'origin_country', 'time_position', 'last_contact',
        'longitude', 'latitude', 'baro_altitude', 'on_ground', 'velocity',
        'true_track', 'vertical_rate', 'sensors', 'geo_altitude', 'squawk', 'spi', 'position_source'
    ]
    df = pd.DataFrame(raw_data, columns=columns)
    
    df = df[['callsign', 'longitude', 'latitude', 'baro_altitude', 'velocity', 'vertical_rate']]
    df = df.dropna(subset=['longitude', 'latitude', 'vertical_rate'])
    df['callsign'] = df['callsign'].astype(str).str.strip().replace('', '알 수 없음')

    mean_vr = df['vertical_rate'].mean()
    std_vr = df['vertical_rate'].std()
    
    if std_vr > 0:
        df['z_score'] = (df['vertical_rate'] - mean_vr) / std_vr
    else:
        df['z_score'] = 0.0

    df['status'] = df['z_score'].apply(lambda z: '위험(급강하)' if z <= z_threshold else '정상')

    def assign_color(status):
        if status == '위험(급강하)':
            return [255, 0, 0, 255] 
        return [255, 200, 0, 180]    
        
    df['color'] = df['status'].apply(assign_color)

    diving_count = len(df[df['status'] == '위험(급강하)'])
    st.sidebar.info(f"📍 현재 추적 비행기: {len(df)}대")
    if diving_count > 0:
        st.sidebar.error(f"⚠️ 급강하 감지: {diving_count}대!!")
    else:
        st.sidebar.success("✅ 현재 특이 이상 징후 없음")

    # -----------------------------------------------------------
    # 4. Pydeck 3D 지도 시각화
    # -----------------------------------------------------------
    view_state = pdk.ViewState(latitude=36.0, longitude=128.0, zoom=6, pitch=45)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[longitude, latitude]",
        get_radius=6000,
        get_fill_color="color",
        pickable=True
    )

    tooltip = {
        "html": """
        <b>콜사인:</b> {callsign} <br/>
        <b>상태:</b> {status} <br/>
        <b>수직 속도:</b> {vertical_rate} m/s <br/>
        <b>Z-score:</b> {z_score} <br/>
        <b>현재 고도:</b> {baro_altitude} m
        """,
        "style": {"backgroundColor": "black", "color": "white"}
    }

    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style="dark"
    )

    st.pydeck_chart(r)
    
    # -----------------------------------------------------------
    # 5. 데이터 테이블 확인
    # -----------------------------------------------------------
    st.subheader("📊 실시간 항공 통계 및 데이터")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="평균 수직 속도", value=f"{mean_vr:.2f} m/s")
    with col2:
        st.metric(label="수직 속도 표준편차", value=f"{std_vr:.2f}")
        
    st.dataframe(df[['callsign', 'status', 'z_score', 'vertical_rate', 'baro_altitude', 'velocity']])
else:
    st.warning("현재 한반도 상공에서 감지된 비행기 데이터가 없습니다. (API 한도 초과이거나 비행기가 없을 수 있습니다.)")
