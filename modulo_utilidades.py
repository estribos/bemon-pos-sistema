import streamlit as st
import pandas as pd
import requests

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyXB8fAsvSVI7gBWkhS6mtks1zPSq_WQs3Rs_wIPoPu_fU-8eLEr7YPnD5mj2ENfJxm/exec"
def run():
    st.header("📊 Dashboard Financiero y Rendimiento")
    st.caption("Resumen en tiempo real de ventas, kilos desplazados y utilidad neta.")

    try:
        resp = requests.get(WEB_APP_URL, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            st.error(payload["error"])
            return
        df_ventas = pd.DataFrame(payload)
    except Exception as e:
        st.error(f"Error al leer la pestaña 'Ventas': {e}")
        return

    if df_ventas is None or df_ventas.empty:
        st.warning("Aún no hay ventas registradas en la base de datos.")
        return

    df_ventas.columns = [str(c).strip() for c in df_ventas.columns]
    col_map = {c.lower(): c for c in df_ventas.columns}

    c_venta = col_map.get("total_venta")
    c_kg = col_map.get("total_kg") or col_map.get("tota_kg")
    c_util = col_map.get("utilidad_neta")
    c_fecha = col_map.get("fecha")

    if not c_venta or not c_kg or not c_util:
        st.error(f"Faltan columnas esperadas en 'Ventas'. Columnas detectadas: {list(df_ventas.columns)}")
        return

    ventas_num = pd.to_numeric(df_ventas[c_venta], errors="coerce").fillna(0.0)
    kg_num = pd.to_numeric(df_ventas[c_kg], errors="coerce").fillna(0.0)
    util_num = pd.to_numeric(df_ventas[c_util], errors="coerce").fillna(0.0)

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Ventas Totales", f"${float(ventas_num.sum()):,.2f} MXN")
    col2.metric("🏗️ Volumen Desplazado", f"{float(kg_num.sum()):,.2f} KG")
    col3.metric("📈 Utilidad Neta Acumulada", f"${float(util_num.sum()):,.2f} MXN")

    st.markdown("---")
    st.subheader("📋 Historial Completo de Ventas (Sincronizado PC y Celular)")

    df_mostrar = df_ventas.copy()
    if c_fecha:
        df_mostrar["_dt_orden"] = pd.to_datetime(df_mostrar[c_fecha], errors="coerce")
        df_mostrar = df_mostrar.sort_values(by="_dt_orden", ascending=False, na_position="last").drop(columns=["_dt_orden"])

    st.dataframe(df_mostrar, use_container_width=True)
