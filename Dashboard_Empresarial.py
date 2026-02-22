import streamlit as st
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro Empresarial")

# --- MAPEAMENTO DOS DADOS (IDs e GIDs) ---
SHEET_ID = "1qIJAdw_aXcVTbf_ELZb5o2dzD8jjUSeKaCPZ6Hzz1rM"
MAPA_GIDS = {
    "2022": "1031075012",
    "2023": "563253526",
    "2024": "239459010",
    "2025": "1647013799",
    "2026": "45417934"
}


# --- FUNÇÃO PARA CARREGAR DADOS ---
@st.cache_data(ttl=60)
def load_data(ano_selecionado):
    gid = MAPA_GIDS.get(ano_selecionado)
    URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    df = pd.read_csv(URL)

    # --- TRATAMENTO DOS DADOS ---
    if 'Valor' in df.columns:
        df['Valor'] = (
            df['Valor']
            .astype(str)
            .str.replace('R$', '', regex=False)
            .str.replace(' ', '', regex=False)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.strip()
        )
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce').fillna(0)

    if 'Data' in df.columns:
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Data']).sort_values('Data')
        df['Mes_Ano'] = df['Data'].dt.strftime('%Y-%m')
        df['Mes_Ano_Exibicao'] = df['Data'].dt.strftime('%m/%Y')
        df['Ano'] = df['Data'].dt.year.astype(str)

    return df


# --- INTERFACE (SIDEBAR E DASHBOARD) ---
st.sidebar.title("Filtros")

# ÚNICO SELETOR DE ANO (Define a aba)
ano_escolhido = st.sidebar.selectbox("Selecione o Ano", list(MAPA_GIDS.keys()))

try:
    df = load_data(ano_escolhido)

    if df.empty:
        st.warning(f"A aba de {ano_escolhido} parece não ter dados válidos.")
    else:
        st.title(f"📊 Dashboard Financeiro - {ano_escolhido}")
        st.sidebar.header("Configurações de Filtro")

        # Filtro de Mês
        df_meses = df[['Mes_Ano_Exibicao', 'Mes_Ano']].drop_duplicates().sort_values('Mes_Ano', ascending=False)
        lista_exibicao = df_meses['Mes_Ano_Exibicao'].tolist()
        mes_visual = st.sidebar.selectbox("Mês de análise detalhada", lista_exibicao)
        mes_selecionado = df_meses.loc[df_meses['Mes_Ano_Exibicao'] == mes_visual, 'Mes_Ano'].values[0]

        ver_tudo = st.sidebar.checkbox("Visualizar histórico anual", value=False)

        # Filtro de Categorias
        lista_cat = sorted([c for c in df["Categoria"].unique().tolist() if c])
        if "selecao_categorias" not in st.session_state:
            st.session_state.selecao_categorias = lista_cat
        if st.sidebar.button("Selecionar todas categorias"):
            st.session_state.selecao_categorias = lista_cat
        cat_escolhidas = st.sidebar.multiselect("Filtrar Categorias", lista_cat, key="selecao_categorias")

        # --- PREPARAÇÃO DOS DADOS ---
        df_mes_base = df[df['Mes_Ano'] == mes_selecionado]
        df_mes = df_mes_base[df_mes_base["Categoria"].isin(cat_escolhidas)]

        is_invest = df_mes['Categoria'].str.contains("Investimento", case=False, na=False)
        df_mes_Receitas = df_mes[((df_mes['Valor'] > 0) & (~is_invest)) | ((df_mes['Valor'] < 0) & (is_invest))]
        df_mes_saidas = df_mes[((df_mes['Valor'] < 0) & (~is_invest)) | ((df_mes['Valor'] > 0) & (is_invest))]

        # DEFINE DATA DE REFERÊNCIA (Necessária para os gráficos)
        data_referencia = df['Data'].min().replace(day=1)

        if ver_tudo:
            df_para_evolucao = df[df["Categoria"].isin(cat_escolhidas)]
            df_para_investimentos = df
            texto_periodo = f"Histórico de {ano_escolhido}"
            intervalo_ms = 30 * 24 * 60 * 60 * 1000
        else:
            df_para_evolucao = df_mes
            df_para_investimentos = df_mes
            texto_periodo = mes_visual
            intervalo_ms = 5 * 24 * 60 * 60 * 1000

        # --- MÉTRICAS ---
        Receitas_total = df_mes_Receitas['Valor'].abs().sum()
        saidas_total_abs = df_mes_saidas['Valor'].abs().sum()
        saldo_mensal = Receitas_total - saidas_total_abs

        data_limite = df_mes_base['Data'].max()
        df_acum_temp = df[df['Data'] <= data_limite].copy()
        is_invest_acum = df_acum_temp['Categoria'].str.contains("Investimento", case=False, na=False)
        df_acum_temp.loc[is_invest_acum, 'Valor'] = -df_acum_temp.loc[is_invest_acum, 'Valor']
        saldo_acumulado = df_acum_temp['Valor'].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Receitas", f"R$ {Receitas_total:,.2f}")
        m2.metric("Despesas", f"R$ {saidas_total_abs:,.2f}")
        m3.metric("Saldo Mensal", f"R$ {saldo_mensal:,.2f}", delta=f"{saldo_mensal:,.2f}")
        m4.metric("Saldo Acumulado", f"R$ {saldo_acumulado:,.2f}", delta=f"{saldo_acumulado:,.2f}")

        st.divider()

        # --- GRÁFICO 1: EVOLUÇÃO FINANCEIRA ---
        st.subheader("📈 Evolução Financeira Detalhada")
        df_para_evolucao = df_para_evolucao.copy()


        def definir_status(row):
            if "Investimento" in str(row['Categoria']):
                return 'Receitas' if row['Valor'] < 0 else 'Despesas'
            return 'Receitas' if row['Valor'] > 0 else 'Despesas'


        df_para_evolucao['Status'] = df_para_evolucao.apply(definir_status, axis=1)
        df_plot = df_para_evolucao.groupby(['Data', 'Status', 'Categoria'])['Valor'].sum().reset_index()
        df_plot['Valor (R$)'] = df_plot['Valor'].abs()

        fig_evolucao = px.line(df_plot, x='Data', y='Valor (R$)', color='Status', markers=True,
                               color_discrete_map={"Receitas": "#2ecc71", "Despesas": "#e74c3c"},
                               template="plotly_dark", custom_data=['Categoria', 'Valor'])

        fig_evolucao.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
        fig_evolucao.update_traces(
            hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Valor:</b> R$ %{customdata[1]:,.2f}<br><b>Cat:</b> %{customdata[0]}<extra></extra>")
        st.plotly_chart(fig_evolucao, use_container_width=True)

        # --- SEÇÃO: EVOLUÇÃO DE INVESTIMENTOS ---
        st.divider()
        st.subheader(f"💰 Evolução de Investimentos ({texto_periodo})")
        df_invest = df_para_investimentos[
            df_para_investimentos["Categoria"].str.contains("Investimento", case=False, na=False)]

        if not df_invest.empty:
            df_invest_plot = df_invest.groupby(['Data', 'Categoria'])['Valor'].sum().reset_index()
            fig_invest = px.line(df_invest_plot, x='Data', y='Valor', color='Categoria', markers=True,
                                 template="plotly_dark")
            fig_invest.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
            st.plotly_chart(fig_invest, use_container_width=True)
        else:
            st.info("Nenhum registro de 'Investimento' encontrado.")

        # --- ÁREA DO CARTÃO DE CRÉDITO ---
        st.divider()
        st.subheader("💳 Área do Cartão de Crédito")


        def calcular_fatura(row):
            dt = row['Data']
            return (dt - pd.DateOffset(months=1)).strftime('%m/%Y') if dt.day <= 2 else dt.strftime('%m/%Y')


        df_cartao_base = df[df['Forma de Pagamento'].str.contains("Cartão de Crédito", case=False, na=False)].copy()

        if not df_cartao_base.empty:
            df_cartao_base['Mes_Fatura'] = df_cartao_base.apply(calcular_fatura, axis=1)
            df_faturas = df_cartao_base.groupby('Mes_Fatura')['Valor'].sum().abs().reset_index()
            valor_fatura_atual = df_faturas.loc[df_faturas['Mes_Fatura'] == mes_visual, 'Valor'].sum()
            st.metric(f"Total da Fatura ({mes_visual})", f"R$ {valor_fatura_atual:,.2f}")

            fig_cartao = px.bar(df_faturas, x='Mes_Fatura', y='Valor', color_discrete_sequence=["#9b59b6"],
                                template="plotly_dark")
            st.plotly_chart(fig_cartao, use_container_width=True)

        # --- ANÁLISES MENSAIS (Distribuição e Balanço) ---
        st.divider()
        st.header("🎯 Análises Mensais")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Distribuição de Gastos")
            if not df_mes_saidas.empty:
                fig_pizza = px.pie(df_mes_saidas, values=df_mes_saidas['Valor'].abs(), names="Categoria", hole=0.4)
                st.plotly_chart(fig_pizza, use_container_width=True)
        with c2:
            st.subheader("Balanço Mensal")
            df_balanco = pd.DataFrame({'Status': ['Receitas', 'Despesas'], 'Total': [Receitas_total, saidas_total_abs]})
            fig_bar = px.bar(df_balanco, x='Status', y='Total', color='Status',
                             color_discrete_map={"Receitas": "#2ecc71", "Despesas": "#e74c3c"})
            st.plotly_chart(fig_bar, use_container_width=True)

        # --- NOVO GRÁFICO: FREQUÊNCIA DOS GASTOS (Antiga Recorrência) ---
        st.subheader("🔄 Frequência dos Gastos")
        # Verifica se a coluna chama 'Frequência' ou 'Frequencia'
        col_freq = 'Frequência' if 'Frequência' in df.columns else (
            'Frequencia' if 'Frequencia' in df.columns else None)

        if col_freq and not df_mes_saidas.empty:
            df_freq = df_mes_saidas.copy()
            df_freq['Valor_Abs'] = df_freq['Valor'].abs()
            # Filtra para não mostrar 'Receitas' caso existam nessa coluna
            df_freq_plot = df_freq[df_freq[col_freq] != 'Receitas'].groupby(col_freq)["Valor_Abs"].sum().reset_index()

            fig_frequencia = px.bar(
                df_freq_plot, x=col_freq, y="Valor_Abs", color=col_freq, template="plotly_dark",
                color_discrete_map={"Fixos": "#5DADE2", "Recorrentes": "#F4D03F", "Não Recorrentes": "#e74c3c"}
            )
            st.plotly_chart(fig_frequencia, use_container_width=True)
        else:
            st.info("Coluna de 'Frequência' não encontrada ou sem dados.")

        # --- RESUMO POR CATEGORIA ---
        st.markdown("### 📋 Resumo de Gastos por Categoria")
        if not df_mes_saidas.empty:
            resumo_cat = df_mes_saidas.groupby("Categoria")["Valor"].sum().abs().reset_index().sort_values(by="Valor",
                                                                                                           ascending=False)
            resumo_final = pd.concat(
                [resumo_cat, pd.DataFrame({"Categoria": ["TOTAL"], "Valor": [resumo_cat["Valor"].sum()]})],
                ignore_index=True)
            st.dataframe(resumo_final.style.format({"Valor": "R$ {:,.2f}"}), use_container_width=True, hide_index=True)

        # --- LISTA DE LANÇAMENTOS ---
        with st.expander(f"🔍 Lista de lançamentos - {mes_visual}"):
            ordem = st.radio("Ordenar por data:", ["Mais recentes", "Mais antigas"], horizontal=True)
            df_lista = df_mes.iloc[:, :-3].copy()
            df_lista = df_lista.sort_values("Data", ascending=(ordem == "Mais antigas"))
            df_lista['Data'] = df_lista['Data'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_lista.style.format({"Valor": "R$ {:,.2f}"}), use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Erro crítico no processamento: {e}")