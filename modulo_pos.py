import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import requests

WEB_APP_URL = "https://script.google.com/macros/s/AKfycbwVXZNjtT5zvf0MHGIgsdJ-Qm07M2-sOLJhHKeBI_PKXoBAZHhiDUn_Aghwx-YPLV7z/exec"
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
    c_kg = col_map.get("total_kg") or col_map.get("tota_kg")
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
            {"medida": "", "kg": 0.0, "precio_kg": 25.0, "importe": 0.0}
        )
        st.rerun()
    if len(st.session_state.partidas_nota) > 1 and c_clr.button("🗑️ Quitar última medida"):
        st.session_state.partidas_nota.pop()
        st.rerun()

    total_kg_nota = 0.0
    total_venta_nota = 0.0
    resumen_partidas = []
    kilos_por_medida = []

    for idx, partida in enumerate(st.session_state.partidas_nota):
        p1, p2, p3, p4 = st.columns([2.0, 1.1, 1.2, 1.2])
        med_sel = p1.text_input(
            f"Medida #{idx + 1}",
            value=str(partida.get("medida", "")),
            placeholder="Ej. 10x15 cm, 12x20 cm, castillo 15x15...",
            key=f"med_{idx}",
        ).strip()
        kg_val = p2.number_input(
            f"Kilos (kg) #{idx + 1}",
            min_value=0.0,
            value=float(partida.get("kg", 0.0)),
            step=1.0,
            key=f"kg_{idx}",
        )
        precio_kg_val = p3.number_input(
            f"Precio/kg ($ MXN) #{idx + 1}",
            min_value=0.0,
            value=float(partida.get("precio_kg", 25.0)),
            step=0.50,
            format="%.2f",
            key=f"pkg_{idx}",
        )
        imp_val = round(kg_val * precio_kg_val, 2)
        p4.metric(f"Importe #{idx + 1}", f"${imp_val:,.2f}")

        st.session_state.partidas_nota[idx] = {
            "medida": med_sel,
            "kg": kg_val,
            "precio_kg": precio_kg_val,
            "importe": imp_val,
        }
        total_kg_nota = round(total_kg_nota + kg_val, 3)
        total_venta_nota = round(total_venta_nota + imp_val, 2)
        if kg_val > 0 or imp_val > 0 or med_sel:
            etiqueta_med = (med_sel if med_sel else f"Medida {idx + 1}").upper()
            resumen_partidas.append(etiqueta_med)
            kilos_por_medida.append(f"{etiqueta_med}={kg_val:g}kg")

    kilos_por_medida_txt = ", ".join(kilos_por_medida)

    costo_material_total = total_kg_nota * costo_base_kg
    utilidad_estimada = total_venta_nota - costo_material_total
    margen_porcentaje = (utilidad_estimada / total_venta_nota * 100) if total_venta_nota > 0 else 0.0
    precio_prom_kg = (total_venta_nota / total_kg_nota) if total_kg_nota > 0 else 0.0

    st.info(
        f"📦 **Total Kilos:** {total_kg_nota:,.2f} kg | **Cobro Total:** ${total_venta_nota:,.2f} MXN | "
        f"**Precio prom./kg:** ${precio_prom_kg:,.2f} | **Costo Alambrón (@ ${costo_base_kg:,.2f}/kg):** ${costo_material_total:,.2f} | "
        f"**Utilidad Neta:** ${utilidad_estimada:,.2f} ({margen_porcentaje:.1f}%)"
    )
    if kilos_por_medida_txt:
        st.caption(f"⚖️ **Kilos por medida:** {kilos_por_medida_txt}")

    if total_venta_nota > 0 and utilidad_estimada < 0:
        st.warning("⚠️ Esta venta arroja **utilidad neta negativa** con el costo de alambrón configurado.")

    # --- DATOS DEL CLIENTE Y CONFIRMACIÓN ---
    with st.form("form_pos_venta", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            folio = st.number_input("Folio de Venta / Nota", min_value=1, value=folio_sugerido, step=1)
            cliente = st.text_input("Cliente / Constructora", placeholder="Ej. Obra Villas / Ing. Pérez")
        with col2:
            metodo_pago = st.selectbox("Método de Pago", ["Efectivo", "Transferencia BANAMEX", "Crédito / Anticipo"])
            nota_extra = st.text_input("Observación / Obra (opcional)", placeholder="Ej. Entrega en obra o anticipo 50%")

        btn_guardar = st.form_submit_button("✅ Registrar Venta y Sincronizar", use_container_width=True)

    if btn_guardar:
        cliente_limpio = cliente.strip()
        errores = []

        if not cliente_limpio:
            errores.append("Ingresa el nombre del cliente o constructora.")
        if total_kg_nota <= 0:
            errores.append("Captura al menos una partida con kilogramos mayores a 0.")
        if total_venta_nota <= 0:
            errores.append("El importe total de la venta debe ser mayor a $0.00 MXN.")
        if int(folio) == st.session_state.ultimo_folio_enviado:
            errores.append(f"El Folio #{int(folio)} ya fue registrado en esta sesión.")

        if errores:
            for err in errores:
                st.error(err)
            return

        obs_final = nota_extra.strip()
        now_dt = datetime.now()
        # Orden exacto de columnas de la hoja Ventas:
        # A: folio | B: fecha | C: cliente | D: medidas | E: kilos_por_medida
        # F: total_kg | G: total_venta | H: utilidad_neta | I: metodo_de_pago | J: observaciones
        payload = {
            "Folio": int(folio),
            "Fecha": now_dt.strftime("%Y-%m-%d"),
            "Cliente": cliente_limpio,
            "Medidas": " | ".join(resumen_partidas),
            "Kilos_Por_Medida": kilos_por_medida_txt,
            "Total_KG": round(float(total_kg_nota), 3),
            "Total_Venta": round(float(total_venta_nota), 2),
            "Utilidad_Neta": round(float(utilidad_estimada), 2),
            "Metodo_Pago": metodo_pago,
            "Observaciones": obs_final,
            "Anio": now_dt.year,
            "Mes_Nombre": MESES_ES[now_dt.month],
        }

        with st.spinner("Sincronizando venta con Google Sheets..."):
            try:
                response = requests.post(WEB_APP_URL, json=payload, timeout=20)
                if response.status_code == 200:
                    data_resp = response.json()
                    if data_resp.get("status") == "ok":
                        st.session_state.ultimo_folio_enviado = int(folio)
                        st.session_state.ventas_sesion.append(payload)
                        st.session_state.partidas_nota = [
                            {"medida": "", "kg": 0.0, "precio_kg": 25.0, "importe": 0.0}
                        ]
                        st.cache_data.clear()
                        st.success(f"¡Venta Folio #{int(folio)} registrada y sincronizada con éxito!")
                        st.rerun()
                    else:
                        st.error(f"Apps Script devolvió error: {data_resp.get('message')}")
                else:
                    st.error(f"Error al sincronizar con la hoja (HTTP {response.status_code}): {response.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

    # --- REGISTRO EN LA APP ---
    if st.session_state.ventas_sesion:
        st.divider()
        st.subheader("🧾 Ventas Registradas en la App")
        cols_vista = ["Folio", "Fecha", "Cliente", "Medidas", "Kilos_Por_Medida", "Total_KG", "Total_Venta", "Utilidad_Neta", "Metodo_Pago"]
        df_vista_sesion = pd.DataFrame(st.session_state.ventas_sesion).reindex(columns=cols_vista).fillna("")
        st.dataframe(df_vista_sesion, use_container_width=True, hide_index=True)

        c_del1, c_del2, c_del3 = st.columns([2, 1.5, 1.5])
        folios_disponibles = [
            f"Folio #{v.get('Folio')} — {v.get('Cliente')} (${float(v.get('Total_Venta', 0)):,.2f})"
            for v in st.session_state.ventas_sesion
        ]
        idx_borrar = c_del1.selectbox(
            "Selecciona una venta de la tabla para quitar",
            options=range(len(folios_disponibles)),
            format_func=lambda i: folios_disponibles[i],
            key="sel_borrar_venta_sesion",
        )
        if c_del2.button("🗑️ Borrar seleccionada", use_container_width=True):
            borrada = st.session_state.ventas_sesion.pop(idx_borrar)
            if st.session_state.ultimo_folio_enviado == borrada.get("Folio"):
                st.session_state.ultimo_folio_enviado = None
            st.rerun()
        if c_del3.button("🧹 Limpiar tabla", use_container_width=True):
            st.session_state.ventas_sesion = []
            st.session_state.ultimo_folio_enviado = None
            st.rerun()

    # --- CONCENTRADO MENSUAL ---
    st.divider()
    st.subheader("📅 Concentrado de Ventas Mensuales")
    if not df_norm.empty and "_dt" in df_norm.columns and df_norm["_dt"].notna().any():
        valid_df = df_norm.dropna(subset=["_dt"]).copy()
        valid_df["Año"] = valid_df["_dt"].dt.year
        valid_df["Mes_Num"] = valid_df["_dt"].dt.month
        valid_df["Mes"] = valid_df["Mes_Num"].map(MESES_ES)

        mensual = (
            valid_df.groupby(["Año", "Mes_Num", "Mes"], as_index=False)
            .agg(
                Kilos_Vendidos=("_kg", "sum"),
                Ventas_MXN=("_venta", "sum"),
                Utilidad_MXN=("_util", "sum"),
                Notas=("_venta", "count"),
            )
            .sort_values(["Año", "Mes_Num"], ascending=[False, False])
        )
        mensual_vista = mensual[["Año", "Mes", "Notas", "Kilos_Vendidos", "Ventas_MXN", "Utilidad_MXN"]].copy()
        mensual_vista["Kilos_Vendidos"] = mensual_vista["Kilos_Vendidos"].map(lambda x: f"{x:,.2f} kg")
        mensual_vista["Ventas_MXN"] = mensual_vista["Ventas_MXN"].map(lambda x: f"${x:,.2f}")
        mensual_vista["Utilidad_MXN"] = mensual_vista["Utilidad_MXN"].map(lambda x: f"${x:,.2f}")
        st.dataframe(mensual_vista, use_container_width=True, hide_index=True)
    else:
        st.caption("Aún no hay ventas con fecha válida para mostrar el concentrado mensual.")
