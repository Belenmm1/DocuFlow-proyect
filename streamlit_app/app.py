"""
streamlit_app/app.py — UI de DocuFlow conectada a la FastAPI.
Correr con: streamlit run streamlit_app/app.py
"""
import streamlit as st
import requests
import time
import json

API_BASE = "http://127.0.0.1:8000/api/v1"

st.set_page_config(
    page_title="DocuFlow",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Syne', sans-serif; }
.block-container { padding-top: 2rem; max-width: 900px; }
.status-badge {
    display: inline-block; padding: 3px 12px;
    border-radius: 100px; font-size: 12px; font-weight: 700;
}
.status-done    { background: #E1F5EE; color: #0F6E56; }
.status-pending { background: #FAEEDA; color: #854F0B; }
.status-processing { background: #E6F1FB; color: #185FA5; }
.status-failed  { background: #FCEBEB; color: #A32D2D; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("## ⚡ DocuFlow")
st.markdown("Subí un documento y la IA extrae, analiza y exporta automáticamente.")
st.divider()

# ── Upload ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    uploaded = st.file_uploader(
        "Seleccioná un archivo",
        type=["pdf", "docx", "xlsx"],
        help="Máximo 20 MB. Formatos: PDF, Word, Excel."
    )

with col2:
    st.markdown("**Formatos soportados**")
    st.markdown("📄 PDF · 📝 DOCX · 📊 XLSX")
    st.markdown("**Pipeline:**")
    st.markdown("Ingesta → Extracción → IA → Reporte")

if uploaded:
    st.divider()

    # 1. Subir documento
    with st.spinner("Subiendo documento..."):
        resp = requests.post(
            f"{API_BASE}/documents/upload",
            files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
        )

    if resp.status_code not in (200, 202):
        st.error(f"Error al subir: {resp.json().get('detail', resp.text)}")
        st.stop()

    doc = resp.json()
    doc_id = doc["id"]
    st.success(f"✅ Documento recibido — ID: `{doc_id}`")

    # 2. Polling hasta done/failed
    progress = st.progress(0, text="Procesando...")
    status = doc["status"]
    steps = {"pending": 10, "processing": 55, "done": 100, "failed": 100}

    for _ in range(40):  # max ~20s de espera
        time.sleep(0.5)
        r = requests.get(f"{API_BASE}/documents/{doc_id}")
        doc = r.json()
        status = doc["status"]
        progress.progress(steps.get(status, 10), text=f"Estado: {status}...")
        if status in ("done", "failed"):
            break

    progress.empty()

    # 3. Resultado
    if status == "failed":
        st.error(f"❌ Falló el procesamiento: {doc.get('error_message', 'Error desconocido')}")
        st.stop()

    st.markdown(f"**Estado:** <span class='status-badge status-done'>✓ done</span>",
                unsafe_allow_html=True)

    # 4. Métricas
    m1, m2, m3 = st.columns(3)
    m1.metric("Páginas", doc.get("page_count", "—"))
    m2.metric("Tamaño", f"{doc.get('size_bytes', 0) / 1024:.1f} KB")
    m3.metric("Tipo", doc.get("file_type", "").upper())

    st.divider()

    # 5. Texto extraído (expandible)
    with st.expander("📄 Texto extraído", expanded=False):
        st.text_area("", doc.get("extracted_text", ""), height=200, disabled=True)

    # 6. Análisis IA (si existe)
    analysis_raw = doc.get("analysis")
    if analysis_raw:
        try:
            analysis = json.loads(analysis_raw) if isinstance(analysis_raw, str) else analysis_raw
        except Exception:
            analysis = {}

        st.markdown("### 🧠 Análisis IA")

        st.info(f"**Resumen:** {analysis.get('resumen', '—')}")

        tipo = analysis.get("tipo_documento", "—")
        score = analysis.get("score_confianza", 0)
        tc1, tc2 = st.columns(2)
        tc1.metric("Tipo de documento", tipo.capitalize())
        tc2.metric("Confianza", f"{float(score):.0%}")

        # Entidades
        entidades = analysis.get("entidades", {})
        if any(entidades.values()):
            st.markdown("**Entidades detectadas**")
            ecols = st.columns(4)
            labels = ["personas", "organizaciones", "fechas", "montos"]
            icons  = ["👤", "🏢", "📅", "💰"]
            for col, label, icon in zip(ecols, labels, icons):
                items = entidades.get(label, [])
                col.markdown(f"**{icon} {label.capitalize()}**")
                col.write("\n".join(items) if items else "—")

        # Campos clave
        campos = analysis.get("campos_clave", {})
        if campos:
            st.markdown("**Campos clave**")
            for k, v in campos.items():
                st.markdown(f"- **{k}:** {v}")

        # Anomalías
        anomalias = analysis.get("anomalias", [])
        if anomalias:
            st.warning("**Anomalías:** " + " · ".join(anomalias))

        st.divider()

        # 7. Exportar
        st.markdown("### 📤 Exportar reporte")
        e1, e2 = st.columns(2)
        with e1:
            xlsx_resp = requests.get(f"{API_BASE}/documents/{doc_id}/export/excel")
            if xlsx_resp.status_code == 200:
                st.download_button(
                    "⬇️ Descargar Excel",
                    data=xlsx_resp.content,
                    file_name=f"docuflow_{doc_id[:8]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        with e2:
            pdf_resp = requests.get(f"{API_BASE}/documents/{doc_id}/export/pdf")
            if pdf_resp.status_code == 200:
                st.download_button(
                    "⬇️ Descargar PDF",
                    data=pdf_resp.content,
                    file_name=f"docuflow_{doc_id[:8]}.pdf",
                    mime="application/pdf",
                )
    else:
        st.info("El análisis IA se activa cuando configurás OPENAI_API_KEY en el .env")

# ── Historial ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 📋 Documentos procesados")

hist = requests.get(f"{API_BASE}/documents/")
if hist.status_code == 200:
    data = hist.json()
    docs = data.get("items", [])
    if docs:
        for d in docs:
            status_class = f"status-{d['status']}"
            with st.container():
                hc1, hc2, hc3, hc4 = st.columns([3, 1, 1, 1])
                hc1.markdown(f"**{d['filename']}**")
                hc2.markdown(f"<span class='status-badge {status_class}'>{d['status']}</span>",
                             unsafe_allow_html=True)
                hc3.markdown(d["file_type"].upper())
                hc4.markdown(f"{d.get('size_bytes', 0) // 1024} KB")
    else:
        st.markdown("_Ningún documento procesado todavía._")
