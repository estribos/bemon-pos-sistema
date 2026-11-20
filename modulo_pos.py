import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import requests

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxRTytCF4E2gnnb2iDc3Rw8-ZN1uOTB8S1dOLRn2dWMn9rVohgldv-uMiNKmCQCapWf/exec"
MESES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL",
    5: "MAYO", 6: "JUNIO", 7: "JULIO", 8: "AGOSTO",
    9: "SEPTIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}


def _cargar_ventas(conn: GSheetsConnection) -> pd.DataFrame:
    try:
        df = conn.read(worksheet="Ventas", ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()


def _normalizar_ventas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    col_map = {c.lower(): c for c in df.columns}
    c_fecha = col_map.get("fecha")
    c_kg = col_map.get("tota_kg") or col_map.get("total_kg")
    c_venta = col_map.get("total_venta")
    c_util = col_map.get("utilidad_neta")
    c_med = col_map.get("medidas") or col_map.get("detalle_medidas")

    out = df.copy()
    out["_dt"] = pd.to_datetime(out[c_fecha], errors="coerce") if c_fecha else pd.NaT
    out["_kg"] = pd.to_numeric(out[c_kg], errors="coerce").fillna(0.0) if c_kg else 0.0
    out["_venta"] = pd.to_numeric(out[c_venta], errors="coerce").fillna(0.0) if c_venta else 0.0
    out["_util"] = pd.to_numeric(out[c_util], errors="coerce").fillna(0.0) if c_util else 0.0
    out["_medidas"] = out[c_med].fillna("").astype(str) if c_med else ""
    return out


def _obtener_siguiente_folio(df: pd.DataFrame) -> int:
    if df.empty:
        return 1
    col_folio = next((c for c in df.columns if c.strip().lower() == "folio"), None)
    if not col_folio:
        return len(df) + 1
    folios_num = pd.to_numeric(df[col_folio], errors="coerce").dropna()
    return int(folios_num.max()) + 1 if not folios_num.empty else 1


def _obtener_costo_kilo(conn: GSheetsConnection) -> tuple[float, str]:
    try:
        df_config = conn.read(worksheet="Configuracion", ttl=0)
        if df_config is not None and not df_config.empty and "Costo_Kilo_Alambron" in df_config.columns:
            valor = float(pd.to_numeric(df_config["Costo_Kilo_Alambron"], errors="coerce").dropna().iloc[0])
            if valor > 0:
                return valor, "Configuracion"
    except Exception:
        pass
    return 18.50, "Base por defecto"


def _calcular_top_medidas(df_norm: pd.DataFrame, top_n: int = 3) -> list[tuple[str, float]]:
    if df_norm.empty or "_medidas" not in df_norm.columns:
        return []
    acumulado: dict[str, float] = {}
    for _, row in df_norm.iterrows():
        texto = str(row.get("_medidas", "")).strip()
        if not texto:
            continue
        kilos_fila = float(row.get("_kg", 0.0) or 0.0)
        partes = [p.strip().upper() for p in texto.split("|") if p.strip()]
        if not partes:
            continue
        peso_por_medida = kilos_fila / len(partes) if kilos_fila > 0 else 0.0
        for nombre_med in partes:
            nombre_limpio = nombre_med.split(":", 1)[0].strip()
            if nombre_limpio:
                acumulado[nombre_limpio] = acumulado.get(nombre_limpio, 0.0) + peso_por_medida
    ordenado = sorted(acumulado.items(), key=lambda x: x[1], reverse=True)
    return ordenado[:top_n]


def run():
    st.header("🛒 Punto de Venta (POS) - Estribos Colima Bemon")
    st.caption("Captura por medida, control diario/mensual de ventas y utilidad, y sincronización con Google Sheets.")

    conn = st.connection("gsheets", type=GSheetsConnection)
    costo_inicial_kg, origen_costo = _obtener_costo_kilo(conn)

    if "costo_alambron_kg" not in st.session_state:
        st.session_state.costo_alambron_kg = float(costo_inicial_kg)
    if "ventas_sesion" not in st.session_state:
        st.session_state.ventas_sesion = []

    df_raw = _cargar_ventas(conn)
    df_norm = _normalizar_ventas(df_raw)

    if st.session_state.ventas_sesion:
        df_sesion = pd.DataFrame(st.session_state.ventas_sesion)
        df_sesion["_dt"] = pd.to_datetime(df_sesion.get("Fecha"), errors="coerce")
        df_sesion["_kg"] = pd.to_numeric(df_sesion.get("Total_KG"), errors="coerce").fillna(0.0)
        df_sesion["_venta"] = pd.to_numeric(df_sesion.get("Total_Venta"), errors="coerce").fillna(0.0)
        df_sesion["_util"] = pd.to_numeric(df_sesion.get("Utilidad_Neta"), errors="coerce").fillna(0.0)
        df_sesion["_medidas"] = df_sesion.get("Medidas", pd.Series("", index=df_sesion.index)).fillna("").astype(str)
        df_norm = pd.concat([df_norm, df_sesion], ignore_index=True)

    folio_sheet = _obtener_siguiente_folio(df_raw)
    folio_sesion = max(
        [int(v.get("Folio", 0)) for v in st.session_state.ventas_sesion] + [0]
    ) + 1
    folio_sugerido = max(folio_sheet, folio_sesion)

    if "ultimo_folio_enviado" not in st.session_state:
        st.session_state.ultimo_folio_enviado = None
    if "partidas_nota" not in st.session_state:
        st.session_state.partidas_nota = [
            {"medida": "", "kg": 0.0, "precio_kg": 25.0, "importe": 0.0}
        ]

    # --- RESUMEN DIARIO, MENSUAL Y UTILIDAD ---
    hoy = datetime.now().date()
    hace_7_dias = hoy - timedelta(days=7)

    if not df_norm.empty and "_dt" in df_norm.columns:
        mask_hoy = df_norm["_dt"].dt.date == hoy
        mask_mes = (df_norm["_dt"].dt.year == hoy.year) & (df_norm["_dt"].dt.month == hoy.month)
        mask_sem = df_norm["_dt"].dt.date >= hace_7_dias

        venta_hoy = float(df_norm.loc[mask_hoy, "_venta"].sum())
        kg_hoy = float(df_norm.loc[mask_hoy, "_kg"].sum())

        venta_mes = float(df_norm.loc[mask_mes, "_venta"].sum())
        kg_mes = float(df_norm.loc[mask_mes, "_kg"].sum())
        util_mes = float(df_norm.loc[mask_mes, "_util"].sum())
        util_sem = float(df_norm.loc[mask_sem, "_util"].sum())
    else:
        venta_hoy = kg_hoy = venta_mes = kg_mes = util_mes = util_sem = 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas de Hoy", f"${venta_hoy:,.2f}", f"{kg_hoy:,.1f} kg hoy")
    m2.metric(f"Ventas {MESES_ES[hoy.month]}", f"${venta_mes:,.2f}", f"{kg_mes:,.1f} kg en el mes")
    m3.metric("Utilidad Semana (7d)", f"${util_sem:,.2f}")
    m4.metric(f"Utilidad {MESES_ES[hoy.month]}", f"${util_mes:,.2f}")

    top_medidas = _calcular_top_medidas(df_norm, top_n=3)
    if top_medidas:
        etiquetas = [f"#{i+1} {med}: {kg:,.1f} kg" for i, (med, kg) in enumerate(top_medidas)]
        st.caption("🏆 **Medidas más vendidas (histórico):** " + "  •  ".join(etiquetas))

    st.divider()

    # --- COSTO DEL KILO DE ALAMBRÓN (AJUSTABLE EN VENTA) ---
    c_costo1, c_costo2 = st.columns([1.5, 3.5])
    costo_base_kg = float(
        c_costo1.number_input(
            "Costo kg Alambrón ($ MXN)",
            min_value=0.0,
            value=float(st.session_state.costo_alambron_kg),
            step=0.50,
            format="%.2f",
            key="input_costo_alambron_kg",
        )
    )
    st.session_state.costo_alambron_kg = costo_base_kg
    c_costo2.caption(
        f"💡 Ajusta aquí el precio actual del kilo de alambrón antes de guardar. "
        f"(Sugerido inicial: ${costo_inicial_kg:,.2f}/kg desde {origen_costo})"
    )

    # --- DESGLOSE POR MEDIDA DE LA VENTA ACTUAL ---
    st.subheader("📐 Desglose por Medida de Estribo")
    c_add, c_clr = st.columns([1, 1])
    if c_add.button("➕ Agregar medida"):
        st.session_state.partidas_nota.append(
            {"medida": "", "kg": 0.0, "precio
