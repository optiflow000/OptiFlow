import streamlit as st
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Dashboard Financeiro Pessoal")

# --- MAPEAMENTO DOS DADOS (IDs e GIDs) ---
SHEET_ID = "1sTGlN690TUp4wDZT93N7HOnvQq9p7pcOpBZE_AhhiSA"
# Dicionário com os GIDs que você mapeou para cada aba
MAPA_GIDS = {
    "2022": "0",
    "2023": "997480959",
    "2024": "1087145999",
    "2025": "268650832",
    "2026": "1031075012"
}


# --- FUNÇÃO PARA CARREGAR DADOS ---
@st.cache_data(ttl=60)
def load_data(ano_selecionado):
    # Busca o GID correspondente ao ano escolhido no dicionário
    gid = MAPA_GIDS.get(ano_selecionado)

    # Monta a URL de exportação CSV dinâmica
    URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"

    # Carrega o CSV direto para o Pandas
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
    # Chama a função passando o ano escolhido pelo usuário
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

        # Lógica para Selecionar Todas as Categorias
        lista_cat = sorted([c for c in df["Categoria"].unique().tolist() if c])

        if "selecao_categorias" not in st.session_state:
            st.session_state.selecao_categorias = lista_cat

        if st.sidebar.button("Selecionar todas categorias"):
            st.session_state.selecao_categorias = lista_cat

        cat_escolhidas = st.sidebar.multiselect("Filtrar Categorias", lista_cat, key="selecao_categorias")

        # --- PREPARAÇÃO DOS DADOS ---
        df_mes_base = df[df['Mes_Ano'] == mes_selecionado]
        df_mes = df_mes_base[df_mes_base["Categoria"].isin(cat_escolhidas)]

        # Criamos uma máscara para identificar o que é investimento
        is_invest = df_mes['Categoria'].str.contains("Investimento", case=False, na=False)

        # Receitas: (Outros > 0) OU (Investimento < 0 [Resgate])
        df_mes_Receitas = df_mes[((df_mes['Valor'] > 0) & (~is_invest)) | ((df_mes['Valor'] < 0) & (is_invest))]

        # Saídas: (Outros < 0) OU (Investimento > 0 [Aplicação])
        df_mes_saidas = df_mes[((df_mes['Valor'] < 0) & (~is_invest)) | ((df_mes['Valor'] > 0) & (is_invest))]

        # DEFINE DATA DE REFERÊNCIA (Necessária para os gráficos)
        data_referencia = df['Data'].min().replace(day=1)

        # --- LÓGICA DE FILTRAGEM POR PERÍODO ---
        if ver_tudo:
            # Filtra os dados apenas para o ano que está selecionado no seletor
            df_para_evolucao = df[(df["Categoria"].isin(cat_escolhidas))]
            df_para_investimentos = df
            texto_periodo = f"Histórico de {ano_escolhido}"
            # Intervalo de 30 dias para não poluir o eixo X em uma visão anual
            intervalo_ms = 30 * 24 * 60 * 60 * 1000
        else:
            # Mantém a visão apenas do mês selecionado
            df_para_evolucao = df_mes
            df_para_investimentos = df_mes
            texto_periodo = mes_visual
            intervalo_ms = 5 * 24 * 60 * 60 * 1000

        # --- MÉTRICAS (AJUSTADAS PARA RESPEITAR O FILTRO ANUAL E LÓGICA DE ACUMULADO ENTRE ANOS) ---
        if ver_tudo:
            df_para_metricas = df[df["Categoria"].isin(cat_escolhidas)].copy()
            label_periodo = "Anual"
            data_limite_acumulado = df['Data'].max()
        else:
            df_para_metricas = df_mes.copy()
            label_periodo = "Mensal"
            data_limite_acumulado = df_mes_base['Data'].max()

        # Identificação de investimentos no set de métricas atual
        is_invest_met = df_para_metricas['Categoria'].str.contains("Investimento", case=False, na=False)

        # Cálculo de Receitas e Despesas do período (mês ou ano)
        rec_periodo = df_para_metricas[
            ((df_para_metricas['Valor'] > 0) & (~is_invest_met)) | ((df_para_metricas['Valor'] < 0) & (is_invest_met))]
        desp_periodo = df_para_metricas[
            ((df_para_metricas['Valor'] < 0) & (~is_invest_met)) | ((df_para_metricas['Valor'] > 0) & (is_invest_met))]

        Receitas_total = rec_periodo['Valor'].abs().sum()
        saidas_total_abs = desp_periodo['Valor'].abs().sum()
        saldo_mensal = Receitas_total - saidas_total_abs

        # --- LÓGICA DE SALDO ACUMULADO (SOMA ANOS ANTERIORES) ---
        saldo_anos_anteriores = 0.0
        invest_anos_anteriores = 0.0
        anos_disponiveis = sorted(list(MAPA_GIDS.keys()))

        for ano in anos_disponiveis:
            if int(ano) < int(ano_escolhido):
                try:
                    df_ant = load_data(ano)
                    if not df_ant.empty:
                        is_invest_ant = df_ant['Categoria'].str.contains("Investimento", case=False, na=False)

                        # Acumulado de Investimentos (Soma direta da coluna Valor onde é investimento)
                        invest_anos_anteriores += df_ant.loc[is_invest_ant, 'Valor'].sum()

                        # Copia para não alterar o cache (Saldo Bancário)
                        df_ant_calc = df_ant.copy()
                        df_ant_calc.loc[is_invest_ant, 'Valor'] = -df_ant_calc.loc[is_invest_ant, 'Valor']
                        saldo_anos_anteriores += df_ant_calc['Valor'].sum()
                except:
                    pass
            else:
                break

        # Saldo do ano atual até a data limite
        df_acum_atual = df[df['Data'] <= data_limite_acumulado].copy()
        is_invest_acum = df_acum_atual['Categoria'].str.contains("Investimento", case=False, na=False)

        # Investimento acumulado atual: Passado + atual
        invest_acumulado_total = invest_anos_anteriores + df_acum_atual.loc[is_invest_acum, 'Valor'].sum()

        df_acum_atual.loc[is_invest_acum, 'Valor'] = -df_acum_atual.loc[is_invest_acum, 'Valor']
        saldo_ano_atual = df_acum_atual['Valor'].sum()

        saldo_acumulado = saldo_anos_anteriores + saldo_ano_atual

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"Receitas ({label_periodo})", f"R$ {Receitas_total:,.2f}")
        m2.metric(f"Despesas ({label_periodo})", f"R$ {saidas_total_abs:,.2f}")
        m3.metric(f"Saldo ({label_periodo})", f"R$ {saldo_mensal:,.2f}", delta=f"{saldo_mensal:,.2f}")
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
                               template="plotly_dark", custom_data=['Categoria', 'Valor'],
                               labels={"Valor (R$)": "Valor (R$)", "Data": "Data"})

        fig_evolucao.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
        fig_evolucao.update_layout(hovermode="closest",
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig_evolucao.update_traces(
            hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Valor Real:</b> R$ %{customdata[1]:,.2f}<br><b>Categoria:</b> %{customdata[0]}<extra></extra>")
        st.plotly_chart(fig_evolucao, use_container_width=True)

        # --- SEÇÃO DE INVESTIMENTOS ---
        st.divider()
        st.subheader(f"📈 Evolução de Investimentos ({texto_periodo})")

        # Filtra os dados apenas para a categoria que contém "Investimento"
        if ver_tudo:
            df_rend = df[df["Categoria"].str.contains("Investimento", case=False, na=False)]
        else:
            df_rend = df_mes_base[df_mes_base["Categoria"].str.contains("Investimento", case=False, na=False)]

        if not df_rend.empty:
            total_rend = df_rend["Valor"].sum()
            st.write(
                f'<p style="font-size:16px; font-weight:bold; margin-bottom: 0px;">Total em Investimentos ({label_periodo}): <span style="color:#2ecc71;">R$ {total_rend:,.2f}</span></p>',
                unsafe_allow_html=True)
            # --- NOVO AJUSTE: Total Atualmente (Acumulado de todos os anos) ---
            st.write(
                f'<p style="font-size:16px; font-weight:bold;">Total Atualmente: <span style="color:#5DADE2;">R$ {invest_acumulado_total:,.2f}</span></p>',
                unsafe_allow_html=True)

            df_rend_plot = df_rend.groupby(['Data', 'Categoria'])['Valor'].sum().reset_index()
            fig_rend = px.line(df_rend_plot, x='Data', y='Valor', color='Categoria', markers=True,
                               template="plotly_dark", color_discrete_sequence=["#2ecc71"],
                               labels={"Valor": "Valor (R$)", "Data": "Data"})

            fig_rend.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
            fig_rend.update_traces(
                hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Valor:</b> R$ %{y:,.2f}<extra></extra>")
            st.plotly_chart(fig_rend, use_container_width=True)
            st.info(f"🍃 Saldo de movimentações em investimentos em {texto_periodo}: R$ {total_rend:,.2f}")
        else:
            st.info("Nenhum registro de 'Investimento' encontrado para este período.")

        # --- ÁREA DO CARTÃO DE CRÉDITO ---
        st.divider()
        st.subheader("💳 Área do Cartão de Crédito")


        def calcular_fatura(row):
            dt = row['Data']
            if dt.day <= 2:
                fatura_dt = dt - pd.DateOffset(months=1)
            else:
                fatura_dt = dt
            return fatura_dt.strftime('%m/%Y')


        # Inclui Cartão de Crédito e Cartão Corporativo conforme detectado na sua planilha
        df_cartao_base = df[
            df['Forma de Pagamento'].str.contains("Cartão de Crédito|Cartão Corporativo", case=False, na=False)].copy()

        if not df_cartao_base.empty:
            df_cartao_base['Mes_Fatura'] = df_cartao_base.apply(calcular_fatura, axis=1)

            df_faturas = df_cartao_base.groupby('Mes_Fatura')['Valor'].sum().abs().reset_index()
            df_faturas['Data_Ref'] = pd.to_datetime(df_faturas['Mes_Fatura'], format='%m/%Y')
            df_faturas = df_faturas.sort_values('Data_Ref')

            valor_fatura_atual = df_faturas.loc[df_faturas['Mes_Fatura'] == mes_visual, 'Valor'].sum()
            st.metric(f"Total da Fatura ({mes_visual})", f"R$ {valor_fatura_atual:,.2f}")

            fig_cartao = px.bar(
                df_faturas,
                x='Mes_Fatura',
                y='Valor',
                title="Visão por Fatura",
                color_discrete_sequence=["#9b59b6"],
                template="plotly_dark",
                labels={"Valor": "Valor da Fatura (R$)", "Mes_Fatura": "Mês da Fatura"}
            )
            fig_cartao.update_traces(
                hovertemplate="<b>Fatura:</b> %{x}<br><b>Valor Total:</b> R$ %{y:,.2f}<extra></extra>"
            )
            st.plotly_chart(fig_cartao, use_container_width=True)

            # Tabela de lançamentos da fatura
            df_fatura_atual = df_cartao_base[df_cartao_base['Mes_Fatura'] == mes_visual].copy()

            if not df_fatura_atual.empty:
                st.markdown(f"**Lançamentos da Fatura de {mes_visual}:**")

                # --- AJUSTE REALIZADO: .fillna("") para remover o "None" da visualização ---
                df_fatura_lista = df_fatura_atual[
                    ['Data', 'Categoria', 'Valor', 'Descrição (Opcional)']].fillna("").copy()
                df_fatura_lista['Data'] = df_fatura_lista['Data'].dt.strftime('%d/%m/%Y')


                def color_valor_custom(val):
                    color = '#2ecc71' if val > 0 else '#e74c3c'
                    return f'color: {color}; font-weight: bold'


                fatura_styled = (
                    df_fatura_lista.style
                    .map(color_valor_custom, subset=['Valor'])
                    .format({"Valor": "R$ {:,.2f}"})
                )
                st.dataframe(fatura_styled, use_container_width=True, hide_index=True)

        # --- ANÁLISES MENSAis ---
        st.divider()
        st.header("🎯 Análises Mensais")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Distribuição de Gastos")
            df_pizza = df_mes_saidas.copy()
            df_pizza['Valor'] = df_pizza['Valor'].abs()
            if not df_pizza.empty:
                fig_pizza = px.pie(
                    df_pizza,
                    values="Valor",
                    names="Categoria",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Plotly
                )
                fig_pizza.update_traces(
                    hovertemplate="<b>Categoria:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<br><b>Percentual:</b> %{percent}<extra></extra>")
                st.plotly_chart(fig_pizza, use_container_width=True)
        with c2:
            st.subheader("Balanço Mensal")
            df_balanco = pd.DataFrame({
                'Status': ['Receitas', 'Despesas'],
                'Total': [Receitas_total, saidas_total_abs]
            })
            fig_bar = px.bar(df_balanco, x='Status', y='Total', color='Status',
                             color_discrete_map={"Receitas": "#2ecc71", "Despesas": "#e74c3c"},
                             labels={"Total": "Valor (R$)"})
            fig_bar.update_traces(hovertemplate="<b>Status:</b> %{x}<br><b>Total:</b> R$ %{y:,.2f}<extra></extra>")
            st.plotly_chart(fig_bar, use_container_width=True)

        # --- GRÁFICO: FREQUÊNCIA DOS GASTOS ---
        st.subheader("🔄 Frequência dos Gastos")

        col_freq = 'Frequência' if 'Frequência' in df.columns else (
            'Frequencia' if 'Frequencia' in df.columns else (
                'Fluxo' if 'Fluxo' in df.columns else None))

        if col_freq and not df_mes_saidas.empty:
            df_freq = df_mes_saidas.copy()
            df_freq['Valor_Abs'] = df_freq['Valor'].abs()

            # --- AJUSTE SOLICITADO: Filtrar apenas as categorias específicas ---
            categorias_alvo = ["Fixos", "Frequentes", "Não Frequentes"]
            df_freq_plot = df_freq[df_freq[col_freq].isin(categorias_alvo)]

            # Agrupamento para o gráfico
            df_freq_plot = df_freq_plot.groupby(col_freq)["Valor_Abs"].sum().reset_index()

            if not df_freq_plot.empty:
                fig_frequencia = px.bar(
                    df_freq_plot,
                    x=col_freq,
                    y="Valor_Abs",
                    color=col_freq,
                    template="plotly_dark",
                    color_discrete_map={
                        "Fixos": "#5DADE2",
                        "Frequentes": "#F4D03F",
                        "Não Frequentes": "#e74c3c"
                    },
                    category_orders={col_freq: categorias_alvo},
                    labels={"Valor_Abs": "Total (R$)", col_freq: "Frequência"}
                )

                fig_frequencia.update_traces(
                    hovertemplate="<b>Tipo:</b> %{x}<br><b>Total:</b> R$ %{y:,.2f}<extra></extra>"
                )
                st.plotly_chart(fig_frequencia, use_container_width=True)
            else:
                st.info("Nenhum gasto encontrado nas categorias: Fixos, Frequentes ou Não Frequentes.")
        else:
            st.info(f"Dados de frequência/fluxo não encontrados na aba de {ano_escolhido}.")

        # --- RESUMO POR CATEGORIA ---
        st.markdown("### 📋 Resumo de Gastos por Categoria")
        if not df_mes_saidas.empty:
            resumo_cat = df_mes_saidas.groupby("Categoria")["Valor"].sum().abs().reset_index().sort_values(by="Valor",
                                                                                                           ascending=False)
            resumo_final = pd.concat(
                [resumo_cat, pd.DataFrame({"Categoria": ["TOTAL"], "Valor": [resumo_cat["Valor"].sum()]})],
                ignore_index=True)


            def highlight_total(row):
                return ['background-color: #990000; color: white; font-weight: bold' if row.Categoria == 'TOTAL' else ''
                        for _ in row]


            st.dataframe(resumo_final.style.apply(highlight_total, axis=1).format({"Valor": "R$ {:,.2f}"}),
                         use_container_width=True, hide_index=True)

        # --- LISTA DE LANÇAMENTOS ---
        with st.expander(f"🔍 Lista de lançamentos - {mes_visual}"):
            col_rec, col_desp = st.columns(2)
            col_rec.markdown(f"**Total Receitas:** <span style='color:#2ecc71'>R$ {Receitas_total:,.2f}</span>",
                             unsafe_allow_html=True)
            col_desp.markdown(
                f"**Total Despesas:** <span style='color:#e74c3c'>R$ {saidas_total_abs:,.2f}</span>",
                unsafe_allow_html=True)

            st.divider()
            ordem = st.radio("Ordenar por data:", ["Mais recentes", "Mais antigas"], horizontal=True)

            df_lista = df_mes.copy()

            # --- AJUSTE: REMOVENDO A COLUNA DASHBOARD ---
            colunas_para_remover = [c for c in df_lista.columns if 'dashboard' in c.lower()]
            if colunas_para_remover:
                df_lista = df_lista.drop(columns=colunas_para_remover)

            df_lista = df_lista.iloc[:, :-3].fillna("")
            df_lista = df_lista.sort_values("Data", ascending=(ordem == "Mais antigas"))
            df_lista['Data'] = df_lista['Data'].dt.strftime('%d/%m/%Y')


            def color_valor_custom(val):
                color = '#2ecc71' if val > 0 else '#e74c3c'
                return f'color: {color}; font-weight: bold'


            st.dataframe(df_lista.style.map(color_valor_custom, subset=['Valor']).format({"Valor": "R$ {:,.2f}"}),
                         use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Erro crítico no processamento: {e}")