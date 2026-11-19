import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.interpolate import griddata
import streamlit as st

st.set_page_config(page_title="Subsurface Borehole & Contour Dashboard", layout="wide")


@st.cache_data
def generate_demo_wells():
    rng = np.random.default_rng(42)
    n = 35
    lats = rng.uniform(57.2, 58.4, n)
    lons = rng.uniform(0.5, 2.2, n)
    formations = rng.choice(["Brent Sand", "Fulmar Sand", "Forties Sand"], size=n)

    # Create a realistic dipping subsurface structure (anticline/dome trend)
    center_lat, center_lon = 57.8, 1.35
    dist = np.sqrt((lats - center_lat) ** 2 + (lons - center_lon) ** 2)
    top_depth = np.round(2150 + 480 * dist + rng.normal(0, 35, n), 1)
    porosity = np.round(np.clip(0.26 - 0.08 * dist + rng.normal(0, 0.025, n), 0.08, 0.34), 3)
    net_pay = np.round(np.clip(45 - 22 * dist + rng.normal(0, 6, n), 5, 65), 1)

    return pd.DataFrame({
        "Well_ID": [f"NS-{i+1:02d}" for i in range(n)],
        "Latitude": np.round(lats, 4),
        "Longitude": np.round(lons, 4),
        "Formation": formations,
        "Top_Depth_m": top_depth,
        "Porosity_vv": porosity,
        "Net_Pay_m": net_pay,
    })


st.title("Subsurface Borehole & Reservoir Mapping Dashboard")
st.caption("Interactive geospatial QC, filtering, and 2D structural/property contouring in Python.")

# Sidebar controls
st.sidebar.header("Data & Filters")
uploaded_file = st.sidebar.file_uploader("Upload Borehole CSV (optional)", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
else:
    df = generate_demo_wells()
    st.sidebar.info("Using built-in North Sea demo dataset (35 wells). Upload a CSV with matching columns to analyze your own data.")

required_cols = {"Well_ID", "Latitude", "Longitude", "Formation", "Top_Depth_m", "Porosity_vv", "Net_Pay_m"}
if not required_cols.issubset(df.columns):
    st.error(f"Uploaded CSV must include columns: {', '.join(sorted(required_cols))}")
    st.stop()

selected_formations = st.sidebar.multiselect(
    "Target Formations",
    options=sorted(df["Formation"].unique()),
    default=sorted(df["Formation"].unique()),
)

min_d, max_d = float(df["Top_Depth_m"].min()), float(df["Top_Depth_m"].max())
depth_range = st.sidebar.slider("Top Depth Range (m)", min_d, max_d, (min_d, max_d))

contour_metric = st.sidebar.selectbox(
    "Contour Map Property",
    options=["Top_Depth_m", "Porosity_vv", "Net_Pay_m"],
    format_func=lambda x: {
        "Top_Depth_m": "Top Reservoir Depth (m)",
        "Porosity_vv": "Porosity (v/v)",
        "Net_Pay_m": "Net Pay Thickness (m)",
    }[x],
)

filtered = df[
    df["Formation"].isin(selected_formations)
    & (df["Top_Depth_m"].between(depth_range[0], depth_range[1]))
]

# Top KPI row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Active Wells", len(filtered))
c2.metric("Mean Top Depth", f"{filtered['Top_Depth_m'].mean():.1f} m" if len(filtered) else "N/A")
c3.metric("Mean Porosity", f"{filtered['Porosity_vv'].mean() * 100:.1f}%" if len(filtered) else "N/A")
c4.metric("Mean Net Pay", f"{filtered['Net_Pay_m'].mean():.1f} m" if len(filtered) else "N/A")

# Two-column visual layout
col_map, col_contour = st.columns(2)

with col_map:
    st.subheader("Geospatial Well Distribution")
    if len(filtered) > 0:
        fig_map = px.scatter_map(
            filtered,
            lat="Latitude",
            lon="Longitude",
            color="Porosity_vv",
            size="Net_Pay_m",
            hover_name="Well_ID",
            hover_data=["Formation", "Top_Depth_m", "Porosity_vv", "Net_Pay_m"],
            color_continuous_scale="Viridis",
            zoom=6,
            height=480,
            map_style="carto-positron",
        )
        fig_map.update_layout(margin={"r": 0, "t": 10, "l": 0, "b": 0})
        st.plotly_chart(fig_map, use_container_width=True)
    else:
        st.warning("No wells match the current filters.")

with col_contour:
    st.subheader(f"2D Interpolated Surface — {contour_metric}")
    if len(filtered) >= 4:
        xi = np.linspace(filtered["Longitude"].min(), filtered["Longitude"].max(), 60)
        yi = np.linspace(filtered["Latitude"].min(), filtered["Latitude"].max(), 60)
        XI, YI = np.meshgrid(xi, yi)
        ZI = griddata(
            (filtered["Longitude"], filtered["Latitude"]),
            filtered[contour_metric],
            (XI, YI),
            method="cubic",
        )

        colorscale = "RdYlBu" if contour_metric == "Top_Depth_m" else "Viridis"
        fig_contour = go.Figure()
        fig_contour.add_trace(
            go.Contour(
                x=xi,
                y=yi,
                z=ZI,
                colorscale=colorscale,
                contours_coloring="heatmap",
                colorbar=dict(title=contour_metric),
            )
        )
        fig_contour.add_trace(
            go.Scatter(
                x=filtered["Longitude"],
                y=filtered["Latitude"],
                mode="markers+text",
                text=filtered["Well_ID"],
                textposition="top center",
                marker=dict(size=7, color="black", line=dict(width=1, color="white")),
                name="Wells",
            )
        )
        fig_contour.update_layout(
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            height=480,
            margin={"r": 10, "t": 10, "l": 10, "b": 10},
        )
        st.plotly_chart(fig_contour, use_container_width=True)
    else:
        st.info("Select at least 4 wells to generate an interpolated 2D contour surface.")

st.subheader("Filtered Well Table")
st.dataframe(filtered, use_container_width=True, hide_index=True)

st.download_button(
    label="Download Filtered Data (CSV)",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_wells.csv",
    mime="text/csv",
)