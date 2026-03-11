import streamlit as st
import os
from pyafipws.wsaa import WSAA
from pyafipws.wsfev1 import WSFEv1
from pyafipws.ws_sr_padron import WSSrPadronA5

st.set_page_config(page_title="Facturador Monotributo ARCA", layout="wide", page_icon="🧾")

# --- FUNCIONES DE SEGURIDAD ---
# --- FUNCIONES DE SEGURIDAD ---
def preparar_certificados():
    try:
        # Extraemos y forzamos el formato de Linux para evitar errores de firma
        cert_content = st.secrets["AFIP_CERT"].replace('\r\n', '\n').strip() + '\n'
        key_content = st.secrets["AFIP_KEY"].replace('\r\n', '\n').strip() + '\n'
        
        with open("temp_cert.crt", "w", encoding='utf-8') as f:
            f.write(cert_content)
        with open("temp_key.key", "w", encoding='utf-8') as f:
            f.write(key_content)
            
        return "temp_cert.crt", "temp_key.key"
    except Exception as e:
        st.error("⚠️ No se encontraron los certificados en los Secrets de Streamlit.")
        return None, None

# --- AUTENTICACIÓN ---
def obtener_ticket_acceso(servicio, entorno, cert_file, key_file):
    wsaa = WSAA()
    url_wsaa = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms?wsdl" if entorno == "Homologación" else "https://wsaa.afip.gov.ar/ws/services/LoginCms?wsdl"
    
    try:
        tra = wsaa.CreateTRA(servicio)
        cms = wsaa.SignTRA(tra, cert_file, key_file)
        wsaa.Conectar(url_wsaa)
        wsaa.LoginCMS(cms)
        return wsaa.Token, wsaa.Sign
    except Exception as e:
        st.error(f"Error de conexión con ARCA: {e}")
        return None, None

# --- INTERFAZ DE USUARIO ---
# --- INTERFAZ DE USUARIO ---
st.title("🧾 Facturador Monotributo (ARCA / AFIP)")

st.sidebar.header("⚙️ Configuración")
entorno = st.sidebar.radio("Entorno de Trabajo", ["Homologación", "Producción"], help="Homologación es para pruebas sin validez fiscal.")
cuit_emisor = st.sidebar.text_input("Tu CUIT (Emisor)", value=st.secrets.get("MI_CUIT", ""))

# Preparar certs al iniciar
cert_path, key_path = preparar_certificados()

tab1, tab2 = st.tabs(["🔍 Consultar Cliente (Padrón)", "📝 Emitir Factura C"])

# --- PESTAÑA 1: PADRÓN ---
with tab1:
    st.header("Consultar CUIT")
    cuit_buscar = st.text_input("Ingrese CUIT del cliente:")
    
    if st.button("Buscar en ARCA"):
        if not cuit_emisor or not cert_path:
            st.warning("Verifique su CUIT y Certificados.")
        else:
            with st.spinner("Buscando..."):
                token, sign = obtener_ticket_acceso("ws_sr_padron_a5", entorno, cert_path, key_path)
                if token:
                    padron = WSSrPadronA5()
                    url_padron = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5?WSDL" if entorno == "Homologación" else "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5?WSDL"
                    padron.Conectar(url_padron)
                    padron.Cuit = cuit_emisor
                    padron.Token = token
                    padron.Sign = sign
                    
                    try:
                        padron.Consultar(cuit_buscar)
                        st.success("Cliente encontrado:")
                        st.write(f"**Razón Social:** {padron.Denominacion}")
                        st.write(f"**Estado:** {padron.Estado}")
                    except Exception as e:
                        st.error("Error al consultar el CUIT. Verifique que sea correcto.")

# --- PESTAÑA 2: FACTURA C ---
with tab2:
    st.header("Emitir Factura C")
    
    col1, col2 = st.columns(2)
    with col1:
        pto_vta = st.number_input("Punto de Venta Web Service", min_value=1, step=1, value=2)
        concepto = st.selectbox("Concepto", ["Productos (1)", "Servicios (2)", "Productos y Servicios (3)"])
        concepto_codigo = int(concepto.split("(")[1][0])
        
    with col2:
        monto_total = st.number_input("Monto Total ($)", min_value=1.0, step=1000.0)
        tipo_doc_receptor = st.selectbox("Documento del Cliente", ["CUIT (80)", "DNI (96)", "Consumidor Final (99)"])
        tipo_doc_codigo = int(tipo_doc_receptor.split("(")[1][:2])
        nro_doc_receptor = st.text_input("Número de Documento", "0")

    if st.button("🚀 Emitir Factura"):
        if not cuit_emisor or not cert_path:
            st.warning("Verifique su CUIT y Certificados.")
        else:
            with st.spinner("Autorizando factura con ARCA..."):
                token, sign = obtener_ticket_acceso("wsfe", entorno, cert_path, key_path)
                
                if token:
                    wsfe = WSFEv1()
                    url_wsfe = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL" if entorno == "Homologación" else "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
                    
                    wsfe.Conectar(url_wsfe)
                    wsfe.Cuit = cuit_emisor
                    wsfe.Token = token
                    wsfe.Sign = sign
                    
                    tipo_cbte_C = 11 
                    wsfe.CompUltimoAutorizado(tipo_cbte_C, pto_vta)
                    
                    try:
                        ultimo_nro = int(wsfe.RespUltimoAutorizado)
                    except:
                        ultimo_nro = 0
                        
                    nuevo_nro = ultimo_nro + 1
                    fecha_hoy = wsfe.FechaActual()
                    
                    wsfe.CrearFactura(
                        concepto=concepto_codigo, tipo_doc=tipo_doc_codigo,
                        nro_doc=nro_doc_receptor, tipo_cbte=tipo_cbte_C,
                        punto_vta=pto_vta, cbt_desde=nuevo_nro, cbt_hasta=nuevo_nro,
                        imp_total=monto_total, imp_neto=monto_total,
                        imp_iva=0.0, imp_trib=0.0, imp_op_ex=0.0, fecha_cbte=fecha_hoy
                    )
                    
                    if concepto_codigo in [2, 3]:
                        wsfe.SetParametros(FchServDesde=fecha_hoy, FchServHasta=fecha_hoy, FchVtoPago=fecha_hoy)

                    try:
                        wsfe.CAESolicitar()
                        if wsfe.Resultado == "A":
                            st.success(f"✅ ¡Factura C N° {nuevo_nro} Autorizada!")
                            st.write(f"**CAE:** {wsfe.CAE}")
                            st.write(f"**Vto CAE:** {wsfe.Vencimiento}")
                        else:
                            st.error("❌ Factura Rechazada.")
                            st.write(f"Error: {wsfe.ErrMsg}")
                            st.write(f"Obs: {wsfe.Obs}")
                    except Exception as e:
                        st.error(f"Error: {e}")
