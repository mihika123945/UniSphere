import pandas as pd
import streamlit as st
import pydeck as pdk
import requests
from dotenv import load_dotenv
import os
load_dotenv()

api_key = os.getenv("api_key")

# Set up the Streamlit page
st.set_page_config(page_title="Study Abroad University Map", layout="wide")

# Load and cache data
@st.cache_data
def load_data():
    df = pd.read_csv("merged_data_with_coordinates.csv")
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["annual_living_cost"] = df["avg_monthly_cost_usd"] * 9
    df["total_estimated_cost"] = df["latest.cost.tuition.out_of_state"] + df["annual_living_cost"]
    return df

df = load_data()

# Layout: split full screen into 2 columns
col1, col2 = st.columns([7, 3])  # 70% for filters/map, 30% for chatbot

with col1:
    # Title and instructions
    st.title("\U0001F30F Study Abroad: U.S. University Explorer")
    st.markdown("Explore U.S. universities by total estimated cost. Adjust filters and click 'Apply Filters' to update the map.")

    # Budget range
    max_budget = int(df["total_estimated_cost"].dropna().max())

    # Additional filters setup
    states = sorted(df["school.state"].dropna().unique())
    min_size, max_size = int(df["latest.student.size"].min()), int(df["latest.student.size"].max())

    # Create form for filters
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

        tooltip = {
            "text": "{school.name}\n{school.city}, {school.state}\nTotal: ${total_estimated_cost}"
        }

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

with col2:
    st.markdown("## 💬 Chat with Study Abroad Bot")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    with st.container():
        chat_container = st.container()
        with chat_container:
            # Apply scroll styling to the chat section
            st.markdown("""
                <style>
                    div[data-testid="stVerticalBlock"] > div:first-child {
                        max-height: 550px;
                        overflow-y: auto;
                        padding-right: 5px;
                    }
                </style>
            """, unsafe_allow_html=True)

            for msg in st.session_state.chat_history:
                role = msg["role"]
                content = msg["content"]

                if role == "user":
                    st.markdown(f"""
                        <div style="text-align: right; margin: 8px 0;">
                            <span style="display: inline-block; background-color: #DCF8C6; color: #000; padding: 8px 12px; border-radius: 15px; max-width: 80%;">{content}</span>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                        <div style="text-align: left; margin: 8px 0;">
                            <span style="display: inline-block; background-color: #F1F0F0; color: #000; padding: 8px 12px; border-radius: 15px; max-width: 80%;">{content}</span>
                        </div>
                    """, unsafe_allow_html=True)

    user_msg = st.chat_input("Type your question here...")

    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})

        api_key = api_key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant for international students studying in the USA."}
            ] + st.session_state.chat_history
        }

        try:
            res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
            reply = res.json()["choices"][0]["message"]["content"]
        except Exception:
            reply = "⚠️ Could not get a response. Try again."

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
