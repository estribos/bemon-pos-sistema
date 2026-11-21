import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection


def run():
    st.header("📊 Dashboard Financiero y Rendimiento")
    st.caption("Resumen en tiempo real de ventas, kilos desplazados y utilidad neta.")

    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_ventas = conn.read(worksheet="Ventas", ttl=0)
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

    if not c_venta or not c_kg or not c_util:
        st.error(
            f"Faltan columnas esperadas en 'Ventas'. Columnas detectadas: {list(df_ventas.columns)}"
        )
        return

    ventas_num = pd.to_numeric(df_ventas[c_venta], errors="coerce").fillna(0.0)
    kg_num = pd.to_numeric(df_ventas[c_kg], errors="coerce").fillna(0.0)
    util_num = pd.to_numeric(df_ventas[c_util], errors="coerce").fillna(0.0)

    total_ingresos = float(ventas_num.sum())
    total_kilos = float(kg_num.sum())
    total_utilidad = float(util_num.sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Ventas Totales", f"${total_ingresos:,.2f} MXN")
    col2.metric("🏗️ Volumen Desplazado", f"{total_kilos:,.2f} KG")
    col3.metric("📈 Utilidad Neta Acumulada", f"${total_utilidad:,.2f} MXN")

    
