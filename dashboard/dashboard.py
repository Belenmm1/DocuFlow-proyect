"""
dashboard.py — Módulo 4: interfaz visual de reportes con Streamlit.

Ejecutar con:
    streamlit run app/dashboard/dashboard.py
"""

import json
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="DocuFlow — Reportes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos custom ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 2rem; color: #534AB7; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #888; }
    .block-container { padding-top: 1.5rem; }
    h1 { color: #534AB7; }
</style>
""", unsafe_allow_html=True)


# ── Helpers API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def fetch_stats() -> dict:
    try:
        r = requests.get(f"{API_BASE}/reports/stats/summary", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"No se pudo conectar con la API: {e}")
        return {}


@st.cache_data(ttl=30)
def fetch_documents(status, file_type, limit: int) -> dict:
    params = {"limit": limit}
    if status and status != "Todos":
        params["status"] = status
    if file_type and file_type != "Todos":
        params["file_type"] = file_type.lower()
    try:
        r = requests.get(f"{API_BASE}/reports/", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error al obtener documentos: {e}")
        return {"total": 0, "items": []}


def download_export(doc_id: str, fmt: str) -> bytes | None:
    try:
        r = requests.get(f"{API_BASE}/reports/{doc_id}/export/{fmt}", timeout=15)
        r.raise_for_status()
        return r.content
    except Exception as e:
        st.error(f"Error al exportar: {e}")
        return None


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://via.placeholder.com/160x40/534AB7/FFFFFF?text=DocuFlow", width=160)
    st.markdown("---")
    st.markdown("### Filtros")

    status_filter = st.selectbox(
        "Estado",
        options=["Todos", "done", "pending", "processing", "failed"],
    )
    type_filter = st.selectbox(
        "Tipo de archivo",
        options=["Todos", "PDF", "DOCX", "XLSX"],
    )
    limit = st.slider("Máximo de resultados", min_value=10, max_value=200, value=50, step=10)

    st.markdown("---")
    if st.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption(f"DocuFlow v0.2.0 · {datetime.now().strftime('%d/%m/%Y %H:%M')}")


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("📊 DocuFlow — Reportes y análisis")
st.caption("Panel de control del pipeline de procesamiento inteligente de documentos.")


# ── Métricas principales ───────────────────────────────────────────────────────

stats = fetch_stats()

if stats:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total documentos",   stats.get("total_documents", 0))
    col2.metric("Procesados hoy",     stats.get("processed_today", 0))
    col3.metric("Completados",        stats.get("done", 0))
    col4.metric("Tasa de éxito",      f"{stats.get('success_rate', 0):.1f}%")
    col5.metric("Entidades extraídas",stats.get("total_entities", 0))

    st.markdown("---")


# ── Gráficos ───────────────────────────────────────────────────────────────────

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Documentos por tipo de archivo")
    by_type = stats.get("by_file_type", {})
    if by_type:
        df_type = pd.DataFrame(
            {"Tipo": list(by_type.keys()), "Cantidad": list(by_type.values())}
        )
        fig_type = px.bar(
            df_type, x="Tipo", y="Cantidad",
            color="Tipo",
            color_discrete_sequence=["#534AB7", "#185FA5", "#0F6E56"],
            text="Cantidad",
        )
        fig_type.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_type, use_container_width=True)
    else:
        st.info("Sin datos de tipos disponibles.")

with col_right:
    st.subheader("Estado del pipeline")
    status_data = {
        "done":       stats.get("done", 0),
        "pending":    stats.get("pending", 0),
        "failed":     stats.get("failed", 0),
    }
    if any(status_data.values()):
        fig_status = go.Figure(data=[go.Pie(
            labels=list(status_data.keys()),
            values=list(status_data.values()),
            hole=0.55,
            marker_colors=["#0F6E56", "#854F0B", "#993C1D"],
        )])
        fig_status.update_layout(margin=dict(t=10, b=10), showlegend=True)
        st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.info("Sin datos de estado disponibles.")


st.markdown("---")


# ── Tabla de documentos ────────────────────────────────────────────────────────

st.subheader("Documentos procesados")

data = fetch_documents(status_filter, type_filter, limit)
items = data.get("items", [])
total = data.get("total", 0)

st.caption(f"Mostrando {len(items)} de {total} documentos")

if items:
    df = pd.DataFrame(items)

    # Formatear columnas
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%d/%m/%Y %H:%M")
    if "size_bytes" in df.columns:
        df["size_kb"] = (df["size_bytes"] / 1024).round(1).astype(str) + " KB"

    display_cols = [c for c in ["filename", "file_type", "status", "page_count", "size_kb", "created_at"] if c in df.columns]

    st.dataframe(
        df[display_cols].rename(columns={
            "filename": "Archivo",
            "file_type": "Tipo",
            "status": "Estado",
            "page_count": "Páginas",
            "size_kb": "Tamaño",
            "created_at": "Procesado",
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No hay documentos que coincidan con los filtros seleccionados.")


st.markdown("---")


# ── Panel de exportación ───────────────────────────────────────────────────────

st.subheader("Exportar análisis")

if items:
    doc_options = {f"{d['filename']} ({d['id'][:8]}…)": d["id"] for d in items if d.get("status") == "done"}

    if doc_options:
        selected_label = st.selectbox("Seleccioná un documento (estado: done)", options=list(doc_options.keys()))
        selected_id = doc_options[selected_label]

        col_xl, col_pdf, col_json = st.columns(3)

        with col_xl:
            if st.button("⬇️ Descargar Excel"):
                with st.spinner("Generando Excel…"):
                    xlsx = download_export(selected_id, "excel")
                if xlsx:
                    st.download_button(
                        "📥 Guardar .xlsx",
                        data=xlsx,
                        file_name=f"docuflow_{selected_id[:8]}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

        with col_pdf:
            if st.button("⬇️ Descargar PDF"):
                with st.spinner("Generando PDF…"):
                    pdf = download_export(selected_id, "pdf")
                if pdf:
                    st.download_button(
                        "📥 Guardar .pdf",
                        data=pdf,
                        file_name=f"docuflow_{selected_id[:8]}.pdf",
                        mime="application/pdf",
                    )

        with col_json:
            if st.button("⬇️ Descargar JSON"):
                with st.spinner("Generando JSON…"):
                    raw = download_export(selected_id, "json")
                if raw:
                    st.download_button(
                        "📥 Guardar .json",
                        data=raw,
                        file_name=f"docuflow_{selected_id[:8]}.json",
                        mime="application/json",
                    )
    else:
        st.warning("No hay documentos en estado 'done' disponibles para exportar.")
else:
    st.info("Cargá documentos primero desde el pipeline de ingesta.")