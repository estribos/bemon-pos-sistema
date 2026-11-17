import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

def run():
    st.header("🛒 Punto de Venta (POS) - Estribos Bemon")
    st.caption("Registra ventas confirmadas y sincroniza en tiempo real con Google Sheets.")

    # Conexión a la base de datos en la nube
    conn = st.connection("gsheets", type=GSheetsConnection)

    # Leer costo actual de materia prima desde la pestaña Configuracion
    try:
        df_config = conn.read(worksheet="Configuracion")
        costo_base_kg = float(df_config["Costo_Kilo_Alambron"].iloc[0])
    except Exception:
        costo_base_kg = 18.50  # Valor base por defecto

    with st.form("form_pos_venta", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            folio = st.number_input("Folio de Venta / Cotización", min_value=1, step=1)
            cliente = st.text_input("Nombre del Cliente / Constructora")
            metodo_pago = st.selectbox("Método de Pago", ["Efectivo", "Transferencia BANAMEX", "Crédito / Anticipo"])

        with col2:
            total_kg = st.number_input("Total de Kilogramos (KG)", min_value=0.1, step=1.0)
            total_venta = st.number_input("Monto Total Cobrado ($ MXN)", min_value=1.0, step=10.0)

        # Cálculos de utilidad
        costo_material_total = total_kg * costo_base_kg
        utilidad_estimada = total_venta - costo_material_total
        margen_porcentaje = (utilidad_estimada / total_venta * 100) if total_venta > 0 else 0

        st.info(f"💡 **Costo estimado material:** ${costo_material_total:,.2f} MXN | **Utilidad Neta:** ${utilidad_estimada:,.2f} MXN ({margen_porcentaje:.1f}%)")

        btn_guardar = st.form_submit_button("✅ Registrar Venta y Sincronizar")

    if btn_guardar:
        if not cliente:
            st.error("Por favor ingresa el nombre del cliente.")
        else:
            nueva_venta = pd.DataFrame([{
                "Folio": folio,
                "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Cliente": cliente,
                "Total_KG": total_kg,
                "Total_Venta": total_venta,
                "Metodo_Pago": metodo_pago,
                "Utilidad_Neta": round(utilidad_estimada, 2)
            }])

            # Leer datos actuales, concatenar y actualizar Google Sheets
            try:
    datos_previos = conn.read(worksheet="Ventas", ttl=0)
except Exception as e:
    st.error(f"Error al conectar con la pestaña Ventas: {e}")
    datos_previos = pd.DataFrame()
            df_actualizado = pd.concat([datos_previos, nueva_venta], ignore_index=True)
            conn.update(worksheet="Ventas", data=df_actualizado)
            
            st.success(f"¡Venta Folio #{folio} registrada y guardada en la nube!")
