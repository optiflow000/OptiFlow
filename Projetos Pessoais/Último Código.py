import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Controle Financeiro Real-Time")


# --- FUNÇÃO PARA CARREGAR DADOS ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]

    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    except Exception:
        try:
            creds = Credentials.from_service_account_file("Projetos Pessoais/credentials.json", scopes=scope)
        except:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scope)

    client = gspread.authorize(creds)
    spreadsheet = client.open("Controle Financeiro Mensal com Gráficos")
    sheet = spreadsheet.worksheet("Controle de Gastos")

    data = sheet.get_all_records()
    df = pd.DataFrame(data)

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

    return df


# --- INTERFACE DO DASHBOARD ---
try:
    df = load_data()

    if df.empty:
        st.warning("Aguardando dados válidos na planilha.")
    else:
        st.title("📊 Meu Dashboard Financeiro")

        # --- SIDEBAR (FILTROS) ---
        st.sidebar.header("Configurações de Filtro")
        df_meses = df[['Mes_Ano_Exibicao', 'Mes_Ano']].drop_duplicates().sort_values('Mes_Ano', ascending=False)
        lista_exibicao = df_meses['Mes_Ano_Exibicao'].tolist()

        mes_visual = st.sidebar.selectbox("Mês de análise detalhada", lista_exibicao)
        mes_selecionado = df_meses.loc[df_meses['Mes_Ano_Exibicao'] == mes_visual, 'Mes_Ano'].values[0]

        ver_tudo = st.sidebar.checkbox("Visualizar todo o histórico no gráfico", value=False)

        # Lógica para Selecionar Todas as Categorias
        lista_cat = sorted([c for c in df["Categoria"].unique().tolist() if c])

        if "selecao_categorias" not in st.session_state:
            st.session_state.selecao_categorias = lista_cat

        if st.sidebar.button("Selecionar todas categorias"):
            st.session_state.selecao_categorias = lista_cat

        cat_escolhidas = st.sidebar.multiselect("Filtrar Categorias", lista_cat, key="selecao_categorias")

        # --- PREPARAÇÃO DOS DADOS (LÓGICA DE FILTRO ADICIONADA) ---
        df_mes_base = df[df['Mes_Ano'] == mes_selecionado]
        df_mes = df_mes_base[df_mes_base["Categoria"].isin(cat_escolhidas)]

        # Criamos uma máscara para identificar o que é investimento
        is_invest = df_mes['Categoria'].str.contains("Investimento", case=False, na=False)

        # Receitas: (Outros > 0) OU (Investimento < 0 [Resgate])
        df_mes_Receitas = df_mes[((df_mes['Valor'] > 0) & (~is_invest)) | ((df_mes['Valor'] < 0) & (is_invest))]

        # Saídas: (Outros < 0) OU (Investimento > 0 [Aplicação])
        df_mes_saidas = df_mes[((df_mes['Valor'] < 0) & (~is_invest)) | ((df_mes['Valor'] > 0) & (is_invest))]

        data_referencia = df['Data'].min().replace(day=1)

        if ver_tudo:
            df_para_evolucao = df[df["Categoria"].isin(cat_escolhidas)]
            df_para_investimentos = df
            texto_periodo = "Histórico Total"
            intervalo_ms = 10 * 24 * 60 * 60 * 1000
        else:
            df_para_evolucao = df_mes
            df_para_investimentos = df_mes
            texto_periodo = mes_visual
            intervalo_ms = 5 * 24 * 60 * 60 * 1000

        # --- MÉTRICAS DO MÊS ---
        # Somamos os valores absolutos para as métricas de exibição
        Receitas_total = df_mes_Receitas['Valor'].abs().sum()
        saidas_total_abs = df_mes_saidas['Valor'].abs().sum()
        saldo_mensal = Receitas_total - saidas_total_abs

        data_limite = df_mes_base['Data'].max()

        # Para o saldo acumulado, precisamos garantir que o investimento positivo subtraia e o negativo some
        df_acum_temp = df[df['Data'] <= data_limite].copy()
        is_invest_acum = df_acum_temp['Categoria'].str.contains("Investimento", case=False, na=False)
        # Invertemos o sinal do investimento para o cálculo do saldo:
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


        # Ajuste do status no gráfico para refletir a nova lógica
        def definir_status(row):
            if "Investimento" in str(row['Categoria']):
                return 'Receitas' if row['Valor'] < 0 else 'Despesas'
            return 'Receitas' if row['Valor'] > 0 else 'Despesas'


        df_para_evolucao['Status'] = df_para_evolucao.apply(definir_status, axis=1)

        df_plot = df_para_evolucao.groupby(['Data', 'Status', 'Categoria'])['Valor'].sum().reset_index()
        df_plot['Valor_Grafico'] = df_plot['Valor'].abs()

        fig_evolucao = px.line(df_plot, x='Data', y='Valor_Grafico', color='Status', markers=True,
                               color_discrete_map={"Receitas": "#2ecc71", "Despesas": "#e74c3c"},
                               category_orders={"Status": ["Receitas", "Despesas"]},
                               template="plotly_dark", custom_data=['Categoria', 'Valor'],
                               labels={"Valor_Grafico": "Valor (R$)", "Data": "Data"})

        fig_evolucao.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
        fig_evolucao.update_layout(hovermode="closest",
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig_evolucao.update_traces(
            hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Valor Real:</b> R$ %{customdata[1]:,.2f}<br><b>Categoria:</b> %{customdata[0]}<extra></extra>")
        st.plotly_chart(fig_evolucao, use_container_width=True)

        # --- SEÇÃO: EVOLUÇÃO DE INVESTIMENTOS ---
        st.divider()
        st.subheader(f"💰 Evolução de Investimentos ({texto_periodo})")

        total_invest_acumulado = df[df["Categoria"].str.contains("Investimento", case=False, na=False)]["Valor"].sum()
        cor_valor = "#2ecc71" if total_invest_acumulado >= 0 else "#e74c3c"
        st.write(
            f'<p style="font-size:16px; font-weight:bold;">Total Investido: <span style="color:{cor_valor};">R$ {total_invest_acumulado:,.2f}</span></p>',
            unsafe_allow_html=True)

        df_invest = df_para_investimentos[
            df_para_investimentos["Categoria"].str.contains("Investimento", case=False, na=False)]

        if not df_invest.empty:
            df_invest_plot = df_invest.groupby(['Data', 'Categoria'])['Valor'].sum().reset_index()
            fig_invest = px.line(df_invest_plot, x='Data', y='Valor', color='Categoria', markers=True,
                                 template="plotly_dark", color_discrete_sequence=px.colors.sequential.Greens_r,
                                 labels={"Valor": "Valor (R$)", "Data": "Data"})

            fig_invest.update_xaxes(tickformat="%d/%m/%Y", dtick=intervalo_ms, tick0=data_referencia, tickmode="linear")
            fig_invest.update_traces(
                hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Movimentação:</b> R$ %{y:,.2f}<extra></extra>")
            st.plotly_chart(fig_invest, use_container_width=True)

            total_inv_periodo = df_invest["Valor"].sum()
            st.info(f"💸 Saldo de movimentações em investimentos em {texto_periodo}: **R$ {total_inv_periodo:,.2f}**")
        else:
            st.info(f"Nenhum registro de 'Investimento' encontrado.")

        # --- NOVA SEÇÃO: ÁREA DO CARTÃO DE CRÉDITO ---
        st.divider()
        st.subheader("💳 Área do Cartão de Crédito")


        # LOGICA DE FECHAMENTO (DIA 03)
        # Se o dia for <= 2, pertence à fatura do mês anterior.
        # Se o dia for > 2, pertence à fatura do mês atual.
        def calcular_fatura(row):
            dt = row['Data']
            if dt.day <= 2:
                fatura_dt = dt - pd.DateOffset(months=1)
            else:
                fatura_dt = dt
            return fatura_dt.strftime('%m/%Y')


        df_cartao_base = df[df['Forma de Pagamento'].str.contains("Cartão de Crédito", case=False, na=False)].copy()

        if not df_cartao_base.empty:
            df_cartao_base['Mes_Fatura'] = df_cartao_base.apply(calcular_fatura, axis=1)

            # Gráfico de Visão de Faturas
            df_faturas = df_cartao_base.groupby('Mes_Fatura')['Valor'].sum().abs().reset_index()
            df_faturas['Data_Ref'] = pd.to_datetime(df_faturas['Mes_Fatura'], format='%m/%Y')
            df_faturas = df_faturas.sort_values('Data_Ref')

            # --- AJUSTE SOLICITADO: VALOR TOTAL DA FATURA ATUAL ABAIXO DO TÍTULO ---
            valor_fatura_atual = df_faturas.loc[df_faturas['Mes_Fatura'] == mes_visual, 'Valor'].sum()
            st.metric(f"Total da Fatura ({mes_visual})", f"R$ {valor_fatura_atual:,.2f}")
            # ----------------------------------------------------------------------

            fig_cartao = px.bar(
                df_faturas,
                x='Mes_Fatura',
                y='Valor',
                title="Visão por Fatura",
                color_discrete_sequence=["#9b59b6"],
                template="plotly_dark",
                labels={"Valor": "Valor da Fatura (R$)", "Mes_Fatura": "Mês da Fatura"}
            )

            # --- AJUSTE SOLICITADO ANTERIORMENTE ---
            fig_cartao.update_traces(
                hovertemplate="<b>Fatura:</b> %{x}<br><b>Valor Total:</b> R$ %{y:,.2f}<extra></extra>"
            )
            # ------------------------------

            st.plotly_chart(fig_cartao, use_container_width=True)

            # Tabela de lançamentos que pertencem à fatura do mês visualizado
            df_fatura_atual = df_cartao_base[df_cartao_base['Mes_Fatura'] == mes_visual].copy()

            if not df_fatura_atual.empty:
                st.markdown(f"**Lançamentos da Fatura de {mes_visual}:**")

                df_fatura_lista = df_fatura_atual[
                    ['Data', 'Categoria', 'Valor', 'Parcelas', 'Descrição (Opcional)']].copy()
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

        # --- SEÇÃO: ANÁLISES MENSAIS ---
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

        # --- NOVO GRÁFICO: RECORRÊNCIA DOS GASTOS ---
        st.subheader("🔄 Recorrência dos Gastos")
        if not df_mes_saidas.empty:
            df_rec = df_mes_saidas.copy()
            df_rec['Valor_Abs'] = df_rec['Valor'].abs()

            df_rec_plot = df_rec[df_rec['Recorrência'] != 'Receitas'].groupby("Recorrência")[
                "Valor_Abs"].sum().reset_index()

            fig_recorrencia = px.bar(
                df_rec_plot,
                x="Recorrência",
                y="Valor_Abs",
                color="Recorrência",
                template="plotly_dark",
                color_discrete_map={
                    "Fixos": "#5DADE2",
                    "Recorrentes": "#F4D03F",
                    "Não Recorrentes": "#e74c3c"
                },
                category_orders={"Recorrência": ["Fixos", "Recorrentes", "Não Recorrentes"]},
                labels={"Valor_Abs": "Total (R$)"}
            )

            fig_recorrencia.update_traces(
                hovertemplate="<b>Recorrência:</b> %{x}<br><b>Total:</b> R$ %{y:,.2f}<extra></extra>"
            )
            st.plotly_chart(fig_recorrencia, use_container_width=True)

        # --- RESUMO POR CATEGORIA ---
        st.markdown("### 📋 Resumo de Gastos por Categoria")
        if not df_mes_saidas.empty:
            resumo_cat = (
                df_mes_saidas.groupby("Categoria")["Valor"]
                .sum()
                .abs()
                .reset_index()
                .sort_values(by="Valor", ascending=False)
            )

            total_gastos = resumo_cat["Valor"].sum()
            linha_total = pd.DataFrame({"Categoria": ["TOTAL"], "Valor": [total_gastos]})
            resumo_final = pd.concat([resumo_cat, linha_total], ignore_index=True)


            def highlight_total(row):
                return ['background-color: #990000; color: white; font-weight: bold' if row.Categoria == 'TOTAL' else ''
                        for _ in row]


            resumo_styled = (
                resumo_final.style
                .apply(highlight_total, axis=1)
                .format({"Valor": "R$ {:,.2f}"})
            )

            st.dataframe(resumo_styled, use_container_width=True, hide_index=True)
        else:
            st.info("Sem gastos registrados para este mês.")

        # --- LISTA DE LANÇAMENTOS COM FILTRO DE ORDENAÇÃO ---
        with st.expander(f"🔍 Lista de lançamentos - {mes_visual}"):

            col_rec, col_desp = st.columns(2)
            col_rec.markdown(f"**Total Receitas:** <span style='color:#2ecc71'>R$ {Receitas_total:,.2f}</span>",
                             unsafe_allow_html=True)
            col_desp.markdown(
                f"**Total Despesas:** <span style='color:#e74c3c'>R$ {saidas_total_abs:,.2f}</span>",
                unsafe_allow_html=True)

            st.divider()

            ordem = st.radio(
                "Ordenar por data:",
                ["Mais recentes", "Mais antigas"],
                horizontal=True
            )

            df_lista = df_mes.iloc[:, :-3].copy()
            ascendente = True if ordem == "Mais antigas" else False
            df_lista = df_lista.sort_values("Data", ascending=ascendente)
            df_lista['Data'] = df_lista['Data'].dt.strftime('%d/%m/%Y')


            def color_valor_custom(val):
                color = '#2ecc71' if val > 0 else '#e74c3c'
                return f'color: {color}; font-weight: bold'


            lista_styled = (
                df_lista.style
                .map(color_valor_custom, subset=['Valor'])
                .format({"Valor": "R$ {:,.2f}"})
            )

            st.dataframe(lista_styled, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Erro crítico no processamento: {e}")