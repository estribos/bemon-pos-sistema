import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

def run():
    st.header("📊 Dashboard Financiero y Rendimiento")
    st.caption("Resumen en tiempo real de ventas, kilos desplazados y utilidad neta.")
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        df_ventas = conn.read(worksheet="Ventas")
    except Exception:
        df_ventas = pd.DataFrame()

    if df_ventas.empty:
        st.warning("Aún no hay ventas registradas en la base de datos.")
        return

    # Limpieza de tipos de datos
    df_ventas["Total_Venta"] = pd.to_numeric(df_ventas["Total_Venta"], errors='coerce')
    df_ventas["Total_KG"] = pd.to_numeric(df_ventas["Total_KG"], errors='coerce')
    df_ventas["Utilidad_Neta"] = pd.to_numeric(df_ventas["Utilidad_Neta"], errors='coerce')

    # Tarjetas ejecutivas
    col1, col2, col3 = st.columns(3)
    
    total_ingresos = df_ventas["Total_Venta"].sum()
    total_kilos = df_ventas["Total_KG"].sum()
    total_utilidad = df_ventas["Utilidad_Neta"].sum()

    col1.metric("💰 Ventas Totales", f"${total_ingresos:,.2f} MXN")
    col2.metric("🏗️ Volumen Desplazado", f"{total_kilos:,.2f} KG")
    col3.metric("📈 Utilidad Neta Acumulada", f"${total_utilidad:,.2f} MXN")

    st.markdown("---")
    st.subheader("📋 Historial Completo de Ventas (Sincronizado PC y Celular)")
    st.dataframe(df_ventas.sort_values(by="Fecha", ascending=False), use_container_width=True)
