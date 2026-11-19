import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import requests

# URL de tu Web App de Google Apps Script recién creada
WEB_APP_URL = https://script.google.com/macros/s/AKfycbzK0ME259N9f8vWAc6h-eDtKUlDypFPNMgT7S7YjKeehaoj-OKyq6T8Is-8xwUWv7L4/exec

def run():
    st.header("🛒 Punto de Venta (POS) - Estribos Bemon")
    st.caption("Registra ventas confirmadas y sincroniza en tiempo real con Google Sheets.")

    # Conexión para leer los datos (esta parte ya te funcionaba perfecto)
    conn = st.connection("gsheets", type=GSheetsConnection)

    # Leer costo actual de materia prima desde la pestaña Configuracion
    try:
        df_config = conn.read(worksheet="Configuracion", ttl=0)
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
            # Estructura del paquete que enviamos por POST a tu Apps Script
            payload = {
                "Folio": int(folio),
                "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Cliente": cliente,
                "Total_KG": float(total_kg),
                "Total_Venta": float(total_venta),
                "Metodo_Pago": metodo_pago,
                "Utilidad_Neta": round(float(utilidad_estimada), 2)
            }

            try:
                # Envía los datos directamente a la hoja "Ventas" mediante tu Web App segura
                response = requests.post(WEB_APP_URL, json=payload)
                if response.status_code == 200:
                    st.success(f"¡Venta Folio #{folio} registrada y guardada en la nube con éxito!")
                else:
                    st.error(f"Error al sincronizar con la hoja: {response.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")
