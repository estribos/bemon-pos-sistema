import streamlit as st

st.set_page_config(page_title="Sistema Integral - Estribos Bemon", layout="wide", page_icon="🏗️")

st.sidebar.title("🏗️ Grupo Bemon")
st.sidebar.subheader("Navegación")

opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    ["📄 Cotizador Oficial", "🛒 Punto de Venta (POS)", "📊 Dashboard Financiero"]
)

if opcion == "📄 Cotizador Oficial":
    import modulo_cotizador
    modulo_cotizador.run()

elif opcion == "🛒 Punto de Venta (POS)":
    import modulo_pos
    modulo_pos.run()

elif opcion == "📊 Dashboard Financiero":
    import modulo_utilidades
    modulo_utilidades.run()
