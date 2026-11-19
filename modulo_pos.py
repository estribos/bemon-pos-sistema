import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import requests

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxAOk4gcRrrwJ_Jw37OAt2M440AVjjyDsw-YAo6o5Gk1YH22pZ19HJN1n_QYvuhEwmP/exec"
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
