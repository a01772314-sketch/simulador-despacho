import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# --- CONFIGURACIÓN DE RUTAS ---
# Esto ayuda a que Python encuentre el archivo motor.py aunque movamos la carpeta
ruta_actual = os.path.dirname(os.path.abspath(__file__))
if ruta_actual not in sys.path:
    sys.path.append(ruta_actual)

# Intentamos importar las funciones del motor
try:
    from motor import run_dispatch, CENACEDataFetcher, VREProfileLoader
except ImportError as e:
    st.error(f"❌ Error de importación: No se encontró motor.py o faltan librerías. {e}")
    st.stop()

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Simulador PyPSA México", layout="wide")

st.title("⚡ Sistema de Despacho Económico (API CENACE + PyPSA)")
st.markdown("""
Esta aplicación se conecta directamente a las bases de datos del **CENACE** usando su API oficial 
para obtener la demanda real y optimizar el despacho con **PyPSA**.
""")
st.markdown("---")

# --- BARRA LATERAL (ENTRADAS) ---
st.sidebar.header("🕹️ Parámetros de Simulación")
st.sidebar.subheader("Costos Marginales (USD/MWh)")
c_gas = st.sidebar.slider("Gas Natural (Térmica)", 30, 80, 45)
c_hidro = st.sidebar.slider("Hidroeléctrica", 0, 20, 5)
c_solar = st.sidebar.slider("Solar PV", 0, 15, 2)

st.sidebar.markdown("---")
st.sidebar.subheader("Configuración de Fechas")
# Usamos una fecha de 2024 que sabemos que tiene datos estables en el API
f_inicio = st.sidebar.date_input("Fecha Inicio", datetime(2024, 10, 15))
f_fin = f_inicio + timedelta(days=1)

# --- CUERPO PRINCIPAL ---
st.subheader("🚀 Ejecución del Modelo")
st.info(f"Se consultarán datos para el sistema **SIN** del {f_inicio} al {f_fin}")

if st.button("CORRER SIMULACIÓN"):
    with st.spinner("Conectando con el API del CENACE y optimizando despacho..."):
        try:
            # 1. Obtener Demanda vía API
            cenace = CENACEDataFetcher()
            demand_df = cenace.fetch_demand('SIN', f_inicio, f_fin)
            
            if demand_df is None or demand_df.empty:
                st.error("El API no devolvió datos. Intenta con otra fecha.")
                st.stop()

            # 2. Preparar el Índice de Tiempo
            time_index = demand_df.index
            sistemas = ['SIN']
            
            # 3. Cargar Perfiles de Renovables (VRE)
            # Asegúrate de que la carpeta 'perfiles_vre' exista en C:\Simulador_Despacho
            ruta_perfiles = Path(ruta_actual) / "perfiles_vre"
            vre_loader = VREProfileLoader(ruta_perfiles)
            vre_profiles = vre_loader.cargar_perfiles(time_index, sistemas)
            
            # 4. Organizar Inputs para el Motor
            inputs = {
                'time_index': time_index,
                'systems': sistemas,
                'demand_MW': {sys: demand_df[sys] for sys in sistemas},
                'vre_pmaxpu': vre_profiles,
                'capacity_MW': {
                    'SIN': {
                        'thermal': 45000, 
                        'solar': 8000, 
                        'hydro': 12000
                    }
                }
            }
            
            params = {
                'marginal_cost_USD_per_MWh': {
                    'thermal': c_gas, 
                    'solar': c_solar, 
                    'hydro': c_hidro
                }
            }

            # 5. Ejecutar Optimización PyPSA
            resultados = run_dispatch(inputs, params)

            # 6. Mostrar Resultados
            if resultados["metadata"]["ok"]:
                st.success("✅ ¡Despacho calculado exitosamente!")
                
                res_sin = resultados["systems"]["SIN"]
                
                # Gráfica de Áreas con Plotly
                fig = go.Figure()
                
                # Añadir cada tecnología a la gráfica
                tecnologias = [
                    ("thermal", "Térmica (Gas)", "#FF4B4B"),
                    ("hydro", "Hidroeléctrica", "#0072B2"),
                    ("solar", "Solar Fotovoltaica", "#F0E442")
                ]
                
                for tech_key, tech_name, color in tecnologias:
                    if tech_key in res_sin["dispatch_MW"]:
                        fig.add_trace(go.Scatter(
                            x=time_index, 
                            y=res_sin["dispatch_MW"][tech_key],
                            name=tech_name,
                            stackgroup='one',
                            line=dict(width=0.5, color=color),
                            fillcolor=color
                        ))

                fig.update_layout(
                    title="Despacho Económico de Energía (MW)",
                    xaxis_title="Tiempo",
                    yaxis_title="Generación (MW)",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Métricas adicionales
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Costo Total Operativo", f"${res_sin['total_cost_USD']:,.2f} USD")
                with col2:
                    demanda_total = demand_df['SIN'].sum()
                    st.metric("Demanda Total Atendida", f"{demanda_total:,.2f} MWh")
            else:
                st.error(f"Error en el motor de optimización: {resultados['metadata'].get('error')}")

        except Exception as e:
            st.error(f"Se produjo un error inesperado: {e}")

st.markdown("---")
st.caption("Desarrollado para simulación de sistemas de potencia con datos reales del CENACE.")