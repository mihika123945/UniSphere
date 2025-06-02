import pandas as pd
import streamlit as st
import pydeck as pdk
from together import Together
from dotenv import load_dotenv
import os
import streamlit.components.v1 as components
import markdown2

# Set up the Streamlit page
st.set_page_config(page_title="Study Abroad University Map", layout="wide")

# Load API key
load_dotenv()
together_api_key = os.getenv("together_api_key")

# Load and cache data
@st.cache_data
def load_data():
    df = pd.read_csv("data/merged_data_with_coordinates.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["annual_living_cost"] = df["avg_monthly_cost_usd"] * 9
    df["total_estimated_cost"] = df["latest.cost.tuition.out_of_state"] + df["annual_living_cost"]
    return df

df = load_data()

# Layout: split full screen into 2 columns
col1, col2 = st.columns([7, 3])  # 70% for filters/map, 30% for chatbot

# --- LEFT SIDE (MAP + FILTERS) ---
with col1:
    st.title("\U0001F30F Study Abroad: U.S. University Explorer")
    st.markdown("Explore U.S. universities by total estimated cost. Adjust filters and click 'Apply Filters' to update the map.")

    max_budget = int(df["total_estimated_cost"].dropna().max())
    states = sorted(df["school.state"].dropna().unique())
    min_size, max_size = int(df["latest.student.size"].min()), int(df["latest.student.size"].max())

    with st.form("filter_form"):
        selected_state = st.selectbox("Filter by State:", ["All"] + states)
        keyword = st.text_input("Search by Program (e.g., Data Science):", "")
        student_range = st.slider("Student Population Range:", min_size, max_size, (min_size, max_size))
        budget = st.slider("Filter by Total Estimated Cost (USD per year):", 10000, max_budget, 40000, step=1000)
        submitted = st.form_submit_button("Apply Filters")

    if submitted:
        filtered_df = df[df["total_estimated_cost"] <= budget]

        if selected_state != "All":
            filtered_df = filtered_df[filtered_df["school.state"] == selected_state]

        if keyword:
            filtered_df = filtered_df[filtered_df["latest.programs.cip_4_digit"].astype(str).str.contains(keyword, case=False)]

        filtered_df = filtered_df[
            (filtered_df["latest.student.size"] >= student_range[0]) &
            (filtered_df["latest.student.size"] <= student_range[1])
        ]

        filtered_df = filtered_df.sample(min(300, len(filtered_df)))
        filtered_df = filtered_df.dropna(subset=["latitude", "longitude", "school.name"])

        if not filtered_df.empty:
            avg_lat = filtered_df["latitude"].mean()
            avg_lon = filtered_df["longitude"].mean()
            zoom_level = 6
        else:
            avg_lat = 37.0902
            avg_lon = -95.7129
            zoom_level = 3

        tooltip = pdk.Tooltip(
            html="""
                <b>{school.name}</b><br/>
                {school.city}, {school.state}<br/>
                Tuition: ${latest.cost.tuition.out_of_state}<br/>
                Total: ${total_estimated_cost}
            """,
            style={"backgroundColor": "white", "color": "black"},
            anchor="top"
        )

        state_layer = None
        if selected_state != "All":
            geojson_url = 'https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_040_00_500k.json'
            response = requests.get(geojson_url)
            if response.status_code == 200:
                us_states = response.json()
                state_geojson = {
                    "type": "FeatureCollection",
                    "features": [
                        feature for feature in us_states["features"]
                        if feature["properties"]["NAME"].lower() == selected_state.lower()
                    ]
                }
                if state_geojson["features"]:
                    state_layer = pdk.Layer(
                        "GeoJsonLayer",
                        state_geojson,
                        stroked=True,
                        filled=True,
                        get_fill_color='[255, 255, 0, 100]',
                        get_line_color='[255, 255, 0]',
                        line_width_min_pixels=2
                    )

        layers = [
            pdk.Layer(
                "ScatterplotLayer",
                data=filtered_df,
                get_position='[longitude, latitude]',
                get_radius=4000,
                get_fill_color='[200, 30, 0, 160]',
                pickable=True,
            )
        ]
        if state_layer:
            layers.append(state_layer)

        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            initial_view_state=pdk.ViewState(
                latitude=avg_lat,
                longitude=avg_lon,
                zoom=zoom_level,
                pitch=0,
            ),
            layers=layers,
            tooltip=tooltip
        ))

        st.markdown(f"Showing {len(filtered_df)} universities under ${budget:,} total estimated cost.")

# --- RIGHT SIDE (CHATBOT + INPUT) ---
with col2:
    st.markdown("## 💬 Chat with Study Abroad Bot")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.form("chat_input_form", clear_on_submit=True):
        user_msg = st.text_input("Type your question here...", key="custom_input")
        submitted = st.form_submit_button("➤")

        if submitted and user_msg:
            st.session_state.chat_history.append({"role": "user", "content": user_msg})

            client = Together(api_key=together_api_key)
            try:
                response = client.chat.completions.create(
                    model="deepseek-ai/DeepSeek-V3",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant for international students."}
                    ] + st.session_state.chat_history,
                    max_tokens=2048,
                    temperature=0.7
                )
                reply = response.choices[0].message.content
            except Exception as e:
                reply = f"⚠️ API error: {e}"

            st.session_state.chat_history.append({"role": "assistant", "content": reply})

    chat_html = """
    <div style='max-height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 10px; background-color: #fff;'>
    """
    for i in range(0, len(st.session_state.chat_history), 2):
        if i < len(st.session_state.chat_history):
            user = markdown2.markdown(st.session_state.chat_history[i]["content"])
            chat_html += f"""
            <div style='text-align: right; margin: 8px 0;'>
                <span style='background-color: #DCF8C6; padding: 8px 12px; border-radius: 15px; display: inline-block; max-width: 80%;'>{user}</span>
            </div>
            """
        if i + 1 < len(st.session_state.chat_history):
            bot = markdown2.markdown(st.session_state.chat_history[i+1]["content"])
            chat_html += f"""
            <div style='text-align: left; margin: 8px 0;'>
                <span style='background-color: #F1F0F0; padding: 8px 12px; border-radius: 15px; display: inline-block; max-width: 80%;'>{bot}</span>
            </div>
            """
    chat_html += "</div>"

    components.html(chat_html, height=420, scrolling=True)
