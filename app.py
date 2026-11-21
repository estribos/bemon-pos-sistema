import streamlit as st

st.set_page_config(page_title="Sistema Integral - Estribos Bemon", layout="wide", page_icon="🏗️")

CLAVE_APP = "BEMON2026"  # Cambia esta por la contraseña que quieras


def verificar_acceso() -> bool:
    if st.session_state.get("app_desbloqueada", False):
        return True

    st.title("🔒 Sistema Integral - Grupo Bemon")
    st.caption("Ingresa tu contraseña para acceder a los módulos y partidas.")

    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        with st.form("form_acceso_general", clear_on_submit=False):
            clave_ingresada = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            if clave_ingresada == CLAVE_APP:
                st.session_state["app_desbloqueada"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")

    return False


if not verificar_acceso():
    st.stop()

st.sidebar.title("🏗️ Grupo Bemon")
st.sidebar.subheader("Navegación")

opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "📄 Cotizador Oficial",
        "🛒 Punto de Venta (POS)",
        "📊 Dashboard Financiero",
        "📦 Compras",
    ]
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

elif opcion == "📦 Compras":
    import compras
    compras.run()
