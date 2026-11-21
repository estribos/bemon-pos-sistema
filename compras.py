import datetime
import pandas as pd
import requests
import streamlit as st

WEB_APP_URL = "TU_URL_EXEC_ACTUALIZADA"


def guardar_compra(payload: dict):
    resp = requests.post(WEB_APP_URL, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not (data.get("ok") or data.get("status") == "ok"):
        raise RuntimeError(data.get("error", "No se pudo guardar la compra."))


def cargar_compras() -> pd.DataFrame:
    resp = requests.get(WEB_APP_URL, params={"hoja": "Compras"}, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload["error"])
    return pd.DataFrame(payload)


def run():
    st.header("📦 Registrar Compra de Material")
    st.caption("Captura entradas de kilos y costo desde computadora o celular.")

    with st.form("form_compra", clear_on_submit=True):
        fecha = st.date_input("Fecha de compra", value=datetime.date.today())
        proveedor = st.text_input("Proveedor", placeholder="Ej. Aceros / Proveedor local")
        kg_comprados = st.number_input(
            "KG comprados",
            min_value=0.0,
            step=1.0,
            format="%.2f",
        )
        costo_total = st.number_input(
            "Costo total ($ MXN)",
            min_value=0.0,
            step=50.0,
            format="%.2f",
        )
        notas = st.text_input("Notas (opcional)", placeholder="Ej. Alambrón 1/4, calibre, remisión...")

        submitted = st.form_submit_button("💾 Guardar compra", use_container_width=True)

    if submitted:
        if kg_comprados <= 0:
            st.warning("Ingresa una cantidad de KG comprados mayor a 0.")
            return

        payload = {
            "Tipo": "Compras",
            "hoja": "Compras",
            "Fecha": fecha.isoformat(),
            "Proveedor": proveedor.strip(),
            "KG_Comprados": float(kg_comprados),
            "Costo_Total": float(costo_total),
            "Notas": notas.strip(),
        }

        try:
            guardar_compra(payload)
            st.success(f"Compra guardada: {kg_comprados:,.2f} KG por ${costo_total:,.2f} MXN.")
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar la compra: {e}")

    st.markdown("---")
    st.subheader("🧾 Últimas compras registradas")

    try:
        df_compras = cargar_compras()
    except Exception as e:
        st.error(f"Error al leer 'Compras': {e}")
        return

    if df_compras.empty:
        st.info("Todavía no hay compras registradas en la pestaña 'Compras'.")
        return

    df_compras.columns = [str(c).strip() for c in df_compras.columns]
    if "Fecha" in df_compras.columns:
        df_compras["_orden"] = pd.to_datetime(df_compras["Fecha"], errors="coerce")
        df_compras = (
            df_compras.sort_values(by="_orden", ascending=False, na_position="last")
            .drop(columns=["_orden"])
        )

    st.dataframe(df_compras, use_container_width=True)
