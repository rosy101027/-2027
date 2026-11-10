import math
import os
import requests
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="대한민국 하천 범람 위험 지도", page_icon="🌧️", layout="wide")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "river_coefficients.csv")

st.title("🇰🇷 대한민국 하천 범람 위험 지도")
st.caption("강수량을 입력하고 하천을 검색해 지역별 참고 위험지수를 지도에서 확인하는 프로젝트")

st.warning(
    "주의: 이 사이트의 값은 학습·시연용 참고 지수이며 실제 범람 확률이나 공식 홍수 예보가 아닙니다. "
    "하상계수와 강수량만으로 실제 범람 여부를 정확히 계산할 수 없습니다. 대피·안전 판단에는 사용하지 마세요."
)

@st.cache_data(ttl=3600)
def load_rivers():
    if not os.path.exists(DATA_PATH):
        return pd.DataFrame(columns=["river_name", "region", "lat", "lon", "bed_coefficient", "source"])
    df = pd.read_csv(DATA_PATH)
    required = ["river_name", "region", "lat", "lon", "bed_coefficient", "source"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"CSV 파일에 '{col}' 열이 없습니다.")
    return df

def geocode_river(query):
    """OpenStreetMap Nominatim을 이용한 이름 검색. 네트워크 연결이 필요합니다."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{query}, 대한민국", "format": "jsonv2", "limit": 5}
    headers = {"User-Agent": "KoreaRiverRiskLearningProject/1.0 (educational app)"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []

def illustrative_index(rain_mm, coefficient):
    """
    데모용 점수. 검증된 홍수확률 모델이 아니며,
    실제 하천별 위험 예측 모델을 대신하지 않습니다.
    """
    rain_score = 100 * (1 - math.exp(-max(0, rain_mm) / 100))
    coeff_score = min(100, 20 * math.log10(1 + max(0, coefficient)))
    return round(0.8 * rain_score + 0.2 * coeff_score, 1)

df = load_rivers()
st.sidebar.header("입력")
rain_mm = st.sidebar.number_input("입력 강수량 (mm)", min_value=0.0, max_value=2000.0, value=50.0, step=5.0)
period = st.sidebar.selectbox("강수량 측정 시간", ["1시간", "3시간", "6시간", "12시간", "24시간", "직접 입력한 누적 강수량"])
st.sidebar.caption("입력한 강수량은 지도에 등록된 모든 하천에 동일하게 적용됩니다.")

st.subheader("하천 검색")
query = st.text_input("하천 이름 입력", placeholder="예: 한강, 낙동강, 금강")
search_clicked = st.button("하천 위치 검색 및 확대", type="primary")

selected_location = None
search_message = ""
if search_clicked and query.strip():
    results = geocode_river(query.strip())
    if results:
        selected_location = (float(results[0]["lat"]), float(results[0]["lon"]))
        search_message = f"검색 결과: {results[0].get('display_name', query)}"
    else:
        search_message = "검색 결과를 찾지 못했습니다. 하천 이름을 다시 확인해 주세요."

if search_message:
    st.info(search_message)

# Search marker or nationwide center
center = selected_location if selected_location else (36.3, 127.8)
zoom = 11 if selected_location else 7
m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)

if not df.empty:
    valid = df.dropna(subset=["lat", "lon"]).copy()
    for _, row in valid.iterrows():
        name = str(row["river_name"])
        region = str(row.get("region", ""))
        coeff = pd.to_numeric(row.get("bed_coefficient"), errors="coerce")
        if pd.notna(coeff) and coeff >= 0:
            score = illustrative_index(rain_mm, float(coeff))
            color = "green" if score < 35 else "orange" if score < 65 else "red"
            popup_text = (
                f"<b>{name}</b><br>{region}<br>"
                f"입력 강수량: {rain_mm:g} mm ({period})<br>"
                f"등록된 하상계수: {coeff:g}<br>"
                f"참고 위험지수: {score}/100<br>"
                f"자료 출처: {row.get('source', '미기재')}"
            )
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=7, color=color, fill=True, fill_opacity=0.75,
                popup=folium.Popup(popup_text, max_width=320),
                tooltip=f"{name} · 참고지수 {score}/100"
            ).add_to(m)
        else:
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=5, color="gray", fill=True, fill_opacity=0.6,
                tooltip=f"{name} · 하상계수 자료 없음"
            ).add_to(m)

if selected_location:
    folium.Marker(
        selected_location, tooltip=f"검색 위치: {query}",
        icon=folium.Icon(color="blue", icon="search")
    ).add_to(m)

st_folium(m, use_container_width=True, height=610, returned_objects=[])

st.subheader("등록된 하천 자료")
if df.empty:
    st.error("아직 하천 자료가 없습니다. data/river_coefficients.csv에 공식 자료를 추가해야 지도에 지역별 하천이 표시됩니다.")
else:
    view = df.copy()
    view["참고 위험지수"] = view["bed_coefficient"].apply(
        lambda x: illustrative_index(rain_mm, float(x)) if pd.notna(pd.to_numeric(x, errors="coerce")) else None
    )
    st.dataframe(view, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("자료를 추가하는 방법")
st.write(
    "data/river_coefficients.csv 파일에 공식 출처로 확인한 하천 자료를 추가하면 지도에 표시됩니다. "
    "하상계수 값과 좌표를 확인할 수 없는 하천은 임의의 숫자를 넣지 말고 비워 두세요."
)
st.caption("지도 검색은 OpenStreetMap Nominatim을 사용합니다. 검색이 안 되거나 인터넷 연결이 없으면 검색 기능이 동작하지 않을 수 있습니다.")
