import pandas as pd
import plotly.express as px
import streamlit as st
import unidecode

DEFAULT_CATEGORY = "nao determinada"
REQUIRED_COLUMNS = {"nm_ingresso_tipo", "valor_pedidos", "total_pedidos"}
TICKET_RELATED_CATEGORIES = {"Ingressos", "Promoções e Vales", "Condições Especiais"}
EVENT_EXPORT_COLUMNS = [
    "id_evento",
    "nm_evento",
    "nm_produtor",
    "nm_sistema_venda",
    "nm_local_evento",
    "nm_localidade_cidade",
    "cd_localidade_estado_sigla",
    "data_inicio_evento",
    "data_fim_evento",
]

# Default keyword mapping for categories
default_categories = {
    "Ingressos": [
        "INGRESSO",
        "TICKET",
        "ENTRADA",
        "PASS",
        "ACESSO",
        "VIP",
        "BACKSTAGE",
        "MEET AND GREET",
    ],
    "Alimentos e Bebidas": [
        "COMIDA",
        "ALIMENTAÇÃO",
        "BEBIDA",
        "BAR",
        "RESTAURANTE",
        "BUFFET",
        "COQUETEL",
        "CERVEJA",
        "VINHO",
        "ÁGUA",
        "REFRIGERANTE",
        "SNACK",
    ],
    "Merchandising": ["CAMISETA", "BONÉ", "POSTER", "SOUVENIR", "LEMBRANÇA", "MERCH", "OFICIAL"],
    "Serviços": ["ESTACIONAMENTO", "SHUTTLE", "TRANSPORTE", "SEGURANÇA", "WI-FI", "GUARDA-VOLUMES", "LOCKER"],
    "Atividades e Experiências": [
        "WORKSHOP",
        "PALESTRA",
        "EXPOSIÇÃO",
        "DEMONSTRAÇÃO",
        "DEGUSTAÇÃO",
        "SHOW",
        "ESPETÁCULO",
        "TEATRO",
        "PERFORMANCE",
        "TOUR",
    ],
    "Acomodações": ["HOSPEDAGEM", "HOTEL", "CAMPING", "ALOJAMENTO"],
    "Promoções e Vales": ["DESCONTO", "PROMOÇÃO", "VALE-PRESENTE", "CUPOM", "EARLY BIRD", "GRÁTIS", "GRATUITA", "VIP"],
    "Condições Especiais": ["MEIA-ENTRADA", "ISENÇÃO", "PCD", "IDOSO", "ESTUDANTE", "PROMO"],
}


def normalize_text(value):
    """Normalize text for reliable keyword matching."""
    text = unidecode.unidecode(str(value or "")).upper().strip()
    return " ".join(text.split())


def prepare_category_mapping(category_mapping):
    """Clean user-provided category rules and remove empty keywords."""
    prepared_mapping = {}

    for category, keywords in category_mapping.items():
        category_name = str(category).strip()
        if not category_name:
            continue

        cleaned_keywords = []
        seen_keywords = set()
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if not normalized_keyword or normalized_keyword in seen_keywords:
                continue
            cleaned_keywords.append(normalized_keyword)
            seen_keywords.add(normalized_keyword)

        if cleaned_keywords:
            prepared_mapping[category_name] = cleaned_keywords

    return prepared_mapping


def classify_sale_type(detected_categories):
    """Map detected categories into business-friendly sale types."""
    if not detected_categories:
        return "nao_determinado"

    ticket_related = [category for category in detected_categories if category in TICKET_RELATED_CATEGORIES]
    non_ticket_related = [category for category in detected_categories if category not in TICKET_RELATED_CATEGORIES]

    if ticket_related and non_ticket_related:
        return "misto"
    if non_ticket_related:
        return "nao_ingresso"
    if ticket_related:
        return "ingresso"
    return "nao_determinado"


def assign_category(name, category_mapping):
    """Assign a primary category and expose uncertainty for review."""
    normalized_name = normalize_text(name)
    if not normalized_name:
        return {
            "categoria": DEFAULT_CATEGORY,
            "categorias_detectadas": DEFAULT_CATEGORY,
            "palavras_chave_encontradas": "",
            "multiplas_categorias": False,
            "tipo_venda_classificada": "nao_determinado",
            "status_revisao": "duvida_sem_match",
        }

    scored_matches = []
    for category, keywords in category_mapping.items():
        matched_keywords = [keyword for keyword in keywords if keyword in normalized_name]
        if matched_keywords:
            scored_matches.append(
                {
                    "categoria": category,
                    "matched_keywords": matched_keywords,
                    "keyword_hits": len(matched_keywords),
                    "total_match_length": sum(len(keyword) for keyword in matched_keywords),
                    "longest_keyword": max(len(keyword) for keyword in matched_keywords),
                }
            )

    if not scored_matches:
        return {
            "categoria": DEFAULT_CATEGORY,
            "categorias_detectadas": DEFAULT_CATEGORY,
            "palavras_chave_encontradas": "",
            "multiplas_categorias": False,
            "tipo_venda_classificada": "nao_determinado",
            "status_revisao": "duvida_sem_match",
        }

    scored_matches.sort(
        key=lambda item: (
            -item["keyword_hits"],
            -item["total_match_length"],
            -item["longest_keyword"],
            item["categoria"],
        )
    )

    best_match = scored_matches[0]
    detected_categories = [match["categoria"] for match in scored_matches]
    found_keywords = []
    for match in scored_matches:
        for keyword in match["matched_keywords"]:
            if keyword not in found_keywords:
                found_keywords.append(keyword)

    sale_type = classify_sale_type(detected_categories)
    if len(detected_categories) > 1:
        review_status = "duvida_multiplas_categorias"
    elif sale_type in {"nao_ingresso", "misto"}:
        review_status = "evento_de_interesse"
    else:
        review_status = "ok"

    return {
        "categoria": best_match["categoria"],
        "categorias_detectadas": ", ".join(detected_categories),
        "palavras_chave_encontradas": ", ".join(found_keywords),
        "multiplas_categorias": len(detected_categories) > 1,
        "tipo_venda_classificada": sale_type,
        "status_revisao": review_status,
    }


def add_analysis_columns(df):
    """Create helper columns used by the analysis views and exports."""
    analysis_df = df.copy()
    analysis_df["flag_evento_interesse"] = analysis_df["tipo_venda_classificada"].isin(["nao_ingresso", "misto"])
    analysis_df["flag_duvida"] = analysis_df["status_revisao"].isin(
        ["duvida_sem_match", "duvida_multiplas_categorias"]
    )
    analysis_df["flag_sem_match"] = analysis_df["status_revisao"].eq("duvida_sem_match")
    analysis_df["flag_multiplas_categorias"] = analysis_df["status_revisao"].eq("duvida_multiplas_categorias")
    analysis_df["valor_evento_interesse"] = analysis_df["valor_pedidos"].where(analysis_df["flag_evento_interesse"], 0.0)
    analysis_df["total_evento_interesse"] = analysis_df["total_pedidos"].where(analysis_df["flag_evento_interesse"], 0.0)
    analysis_df["valor_duvida"] = analysis_df["valor_pedidos"].where(analysis_df["flag_duvida"], 0.0)
    analysis_df["total_duvida"] = analysis_df["total_pedidos"].where(analysis_df["flag_duvida"], 0.0)
    analysis_df["chave_produto"] = (
        analysis_df["id_ingresso_tipo"].astype(str) if "id_ingresso_tipo" in analysis_df.columns else analysis_df["nm_ingresso_tipo"]
    )
    return analysis_df


def load_and_categorize(uploaded_files, category_mapping):
    """Load CSV files, validate schema, and classify each product."""
    prepared_mapping = prepare_category_mapping(category_mapping)
    if not prepared_mapping:
        raise ValueError("Configure pelo menos uma categoria com palavras-chave válidas.")

    all_dataframes = []
    processing_errors = []

    for uploaded_file in uploaded_files:
        try:
            df = pd.read_csv(uploaded_file)
        except Exception as exc:
            processing_errors.append(f"Não foi possível ler `{uploaded_file.name}`: {exc}")
            continue

        df.columns = df.columns.str.strip()
        missing_columns = REQUIRED_COLUMNS.difference(df.columns)
        if missing_columns:
            missing_columns_text = ", ".join(sorted(missing_columns))
            processing_errors.append(f"`{uploaded_file.name}` não contém as colunas obrigatórias: {missing_columns_text}")
            continue

        df = df.copy()
        df["arquivo_origem"] = uploaded_file.name
        df["nm_ingresso_tipo"] = df["nm_ingresso_tipo"].fillna("").astype(str)
        df["valor_pedidos"] = pd.to_numeric(df["valor_pedidos"], errors="coerce").fillna(0.0)
        df["total_pedidos"] = pd.to_numeric(df["total_pedidos"], errors="coerce").fillna(0.0)

        classification = df["nm_ingresso_tipo"].apply(lambda name: assign_category(name, prepared_mapping))
        classification_df = pd.DataFrame(classification.tolist())
        df = pd.concat([df.reset_index(drop=True), classification_df], axis=1)
        all_dataframes.append(df)

    if not all_dataframes:
        raise ValueError("Nenhum arquivo válido foi processado.")

    combined_df = pd.concat(all_dataframes, ignore_index=True)
    return add_analysis_columns(combined_df), processing_errors, prepared_mapping


def get_event_group_columns(df):
    """Use event metadata when available, otherwise fall back to the source file."""
    available_columns = [column for column in EVENT_EXPORT_COLUMNS if column in df.columns]
    return available_columns or ["arquivo_origem"]


def build_event_summary(df):
    """Aggregate row-level classifications into event-level review datasets."""
    group_columns = get_event_group_columns(df)
    event_summary = (
        df.groupby(group_columns, dropna=False)
        .agg(
            total_linhas=("nm_ingresso_tipo", "count"),
            produtos_distintos=("chave_produto", "nunique"),
            categorias_distintas=("categoria", "nunique"),
            receita_total=("valor_pedidos", "sum"),
            pedidos_total=("total_pedidos", "sum"),
            receita_evento_interesse=("valor_evento_interesse", "sum"),
            pedidos_evento_interesse=("total_evento_interesse", "sum"),
            receita_duvida=("valor_duvida", "sum"),
            pedidos_duvida=("total_duvida", "sum"),
            linhas_com_duvida=("flag_duvida", "sum"),
            linhas_sem_match=("flag_sem_match", "sum"),
            linhas_multiplas_categorias=("flag_multiplas_categorias", "sum"),
            linhas_nao_ingresso=("tipo_venda_classificada", lambda series: (series == "nao_ingresso").sum()),
            linhas_mistas=("tipo_venda_classificada", lambda series: (series == "misto").sum()),
        )
        .reset_index()
    )

    event_summary["share_receita_evento_interesse"] = (
        event_summary["receita_evento_interesse"] / event_summary["receita_total"].replace(0, pd.NA)
    ).fillna(0.0)
    event_summary["evento_de_interesse"] = event_summary["receita_evento_interesse"] > 0
    event_summary["evento_com_duvida"] = event_summary["linhas_com_duvida"] > 0

    return event_summary.sort_values(
        ["receita_evento_interesse", "receita_duvida", "receita_total"],
        ascending=[False, False, False],
    )


def build_focus_dataset(df, focus_mode, selected_sale_types, selected_categories):
    """Apply simple business-driven filters before rendering the views."""
    filtered_df = df.copy()

    if focus_mode == "Somente oportunidades":
        filtered_df = filtered_df[filtered_df["flag_evento_interesse"]]
    elif focus_mode == "Somente dúvidas":
        filtered_df = filtered_df[filtered_df["flag_duvida"]]
    elif focus_mode == "Oportunidades + dúvidas":
        filtered_df = filtered_df[filtered_df["flag_evento_interesse"] | filtered_df["flag_duvida"]]

    if selected_sale_types:
        filtered_df = filtered_df[filtered_df["tipo_venda_classificada"].isin(selected_sale_types)]
    if selected_categories:
        filtered_df = filtered_df[filtered_df["categoria"].isin(selected_categories)]

    return filtered_df


def plot_category_breakdown(df):
    """Show how the focused dataset distributes across categories."""
    if df.empty:
        st.info("Nenhum registro disponível para as categorias selecionadas.")
        return

    category_sums = (
        df.groupby("categoria", as_index=False)[["valor_pedidos", "total_pedidos"]]
        .sum()
        .sort_values("valor_pedidos", ascending=False)
    )
    fig_valor = px.bar(
        category_sums,
        x="categoria",
        y="valor_pedidos",
        title="Receita por categoria principal",
        text_auto=".2s",
    )
    st.plotly_chart(fig_valor, use_container_width=True)

    fig_total = px.bar(
        category_sums.sort_values("total_pedidos", ascending=False),
        x="categoria",
        y="total_pedidos",
        title="Pedidos por categoria principal",
        text_auto=".2s",
    )
    st.plotly_chart(fig_total, use_container_width=True)


def plot_sale_type_breakdown(df):
    """Show the split between ticket and non-ticket-like rows."""
    if df.empty:
        st.info("Nenhum registro disponível para o recorte selecionado.")
        return

    sale_type_summary = (
        df.groupby("tipo_venda_classificada", as_index=False)[["valor_pedidos", "total_pedidos"]]
        .sum()
        .sort_values("valor_pedidos", ascending=False)
    )
    fig = px.bar(
        sale_type_summary,
        x="tipo_venda_classificada",
        y="valor_pedidos",
        color="tipo_venda_classificada",
        title="Receita por tipo de venda classificada",
        text_auto=".2s",
    )
    st.plotly_chart(fig, use_container_width=True)


def show_summary_metrics(df, event_summary):
    """Display top-level metrics focused on non-ticket discovery and rule tuning."""
    total_receita = float(df["valor_pedidos"].sum())
    receita_interesse = float(df["valor_evento_interesse"].sum())
    receita_duvida = float(df["valor_duvida"].sum())
    eventos_interesse = int(event_summary["evento_de_interesse"].sum())
    eventos_duvida = int(event_summary["evento_com_duvida"].sum())

    metric_columns = st.columns(5)
    metric_columns[0].metric("Receita analisada", f"R$ {total_receita:,.0f}".replace(",", "."))
    metric_columns[1].metric("Receita em oportunidade", f"R$ {receita_interesse:,.0f}".replace(",", "."))
    metric_columns[2].metric("Receita com dúvida", f"R$ {receita_duvida:,.0f}".replace(",", "."))
    metric_columns[3].metric("Eventos de interesse", eventos_interesse)
    metric_columns[4].metric("Eventos com dúvida", eventos_duvida)


def edit_keywords(categories):
    """Allow dynamic modification of category keywords."""
    updated_categories = {}
    for category, keywords in categories.items():
        user_input = st.text_area(
            f"Palavras-chave para {category}",
            ", ".join(keywords),
            key=f"keywords_{category}",
        )
        updated_categories[category] = [keyword.strip() for keyword in user_input.split(",")]

    new_category_name = st.text_input("Adicionar Nova Categoria (Nome da Categoria)")
    new_category_keywords = st.text_area("Palavras-chave para Nova Categoria (separadas por vírgula)")
    if new_category_name and new_category_keywords:
        updated_categories[new_category_name] = [keyword.strip() for keyword in new_category_keywords.split(",")]

    return updated_categories


def to_csv_bytes(df):
    """Export dataframes as UTF-8 CSV."""
    return df.to_csv(index=False).encode("utf-8")


def main():
    st.set_page_config(page_title="Análise de Categorias de Produtos", layout="wide")
    st.title("Detector de vendas além de ingressos")
    st.caption(
        "Use o nome do produto para encontrar vendas não relacionadas a ingresso, destacar eventos com potencial e revisar casos ambíguos para melhorar as regras."
    )

    uploaded_files = st.file_uploader("Escolha os arquivos CSV", type="csv", accept_multiple_files=True)

    with st.expander("Configurações de categorias", expanded=not uploaded_files):
        st.subheader("Edite as palavras-chave")
        updated_categories = edit_keywords(default_categories)
        prepared_mapping = prepare_category_mapping(updated_categories)
        st.subheader("Mapa de categorias válido")
        st.json(prepared_mapping)

    if not uploaded_files:
        st.info("Envie um ou mais arquivos CSV para iniciar a análise.")
        return

    try:
        df, processing_errors, _prepared_mapping = load_and_categorize(uploaded_files, updated_categories)
    except ValueError as exc:
        st.error(str(exc))
        return

    if processing_errors:
        for error_message in processing_errors:
            st.warning(error_message)

    event_summary = build_event_summary(df)
    interest_events = event_summary[event_summary["evento_de_interesse"]].copy()
    doubt_events = event_summary[event_summary["evento_com_duvida"]].copy()

    st.success(f"Arquivos processados com sucesso. {len(df)} registros válidos foram analisados.")
    show_summary_metrics(df, event_summary)

    st.subheader("Filtros rápidos")
    filter_columns = st.columns([1.3, 1, 1])
    focus_mode = filter_columns[0].radio(
        "Recorte principal",
        ["Tudo", "Somente oportunidades", "Somente dúvidas", "Oportunidades + dúvidas"],
        horizontal=True,
    )
    selected_sale_types = filter_columns[1].multiselect(
        "Tipo de venda",
        sorted(df["tipo_venda_classificada"].unique().tolist()),
        default=[],
        placeholder="Todos",
    )
    selected_categories = filter_columns[2].multiselect(
        "Categoria principal",
        sorted(df["categoria"].unique().tolist()),
        default=[],
        placeholder="Todas",
    )

    filtered_df = build_focus_dataset(df, focus_mode, selected_sale_types, selected_categories)
    filtered_event_summary = build_event_summary(filtered_df) if not filtered_df.empty else event_summary.iloc[0:0].copy()
    filtered_interest_events = filtered_event_summary[filtered_event_summary["evento_de_interesse"]].copy()
    filtered_doubt_events = filtered_event_summary[filtered_event_summary["evento_com_duvida"]].copy()

    tabs = st.tabs(
        [
            "Visão geral",
            "Eventos de interesse",
            "Dúvidas para refinar",
            "Dados completos",
        ]
    )

    with tabs[0]:
        st.subheader("Panorama do recorte selecionado")
        if filtered_df.empty:
            st.info("Nenhum registro encontrado para os filtros selecionados.")
        else:
            plot_sale_type_breakdown(filtered_df)
            plot_category_breakdown(filtered_df)

            top_interest_rows = filtered_df[filtered_df["flag_evento_interesse"]].nlargest(20, "valor_pedidos")
            if not top_interest_rows.empty:
                st.markdown("#### Produtos com maior potencial de venda além de ingresso")
                st.dataframe(
                    top_interest_rows[
                        [
                            column
                            for column in [
                                "arquivo_origem",
                                "id_evento",
                                "nm_evento",
                                "nm_produtor",
                                "nm_ingresso_tipo",
                                "categoria",
                                "tipo_venda_classificada",
                                "palavras_chave_encontradas",
                                "valor_pedidos",
                                "total_pedidos",
                            ]
                            if column in top_interest_rows.columns
                        ]
                    ],
                    use_container_width=True,
                )

    with tabs[1]:
        st.subheader("Eventos de interesse")
        st.caption("Eventos que possuem ao menos um item classificado como `nao_ingresso` ou `misto`.")
        if filtered_interest_events.empty:
            st.info("Nenhum evento de interesse encontrado para o recorte selecionado.")
        else:
            st.dataframe(filtered_interest_events, use_container_width=True)
            st.download_button(
                label="Baixar eventos de interesse",
                data=to_csv_bytes(filtered_interest_events),
                file_name="eventos_de_interesse.csv",
                mime="text/csv",
            )

    with tabs[2]:
        st.subheader("Dúvidas para refinar filtros")
        st.caption("Casos sem match ou com múltiplas categorias detectadas, úteis para evoluir as regras.")

        doubt_rows = filtered_df[filtered_df["flag_duvida"]].copy()
        if doubt_rows.empty:
            st.success("Nenhum caso duvidoso encontrado para o recorte selecionado.")
        else:
            st.markdown("#### Eventos com dúvidas")
            st.dataframe(filtered_doubt_events, use_container_width=True)
            st.download_button(
                label="Baixar eventos com dúvidas",
                data=to_csv_bytes(filtered_doubt_events),
                file_name="eventos_com_duvidas.csv",
                mime="text/csv",
            )

            st.markdown("#### Linhas para revisão de regra")
            review_columns = [
                column
                for column in [
                    "arquivo_origem",
                    "id_evento",
                    "nm_evento",
                    "nm_produtor",
                    "nm_ingresso_tipo",
                    "categoria",
                    "categorias_detectadas",
                    "palavras_chave_encontradas",
                    "tipo_venda_classificada",
                    "status_revisao",
                    "valor_pedidos",
                    "total_pedidos",
                ]
                if column in doubt_rows.columns
            ]
            st.dataframe(doubt_rows[review_columns], use_container_width=True)
            st.download_button(
                label="Baixar linhas com dúvidas",
                data=to_csv_bytes(doubt_rows[review_columns]),
                file_name="linhas_com_duvidas.csv",
                mime="text/csv",
            )

    with tabs[3]:
        st.subheader("Base categorizada")
        preview_columns = [
            column
            for column in [
                "arquivo_origem",
                "id_evento",
                "nm_evento",
                "nm_produtor",
                "nm_ingresso_tipo",
                "categoria",
                "tipo_venda_classificada",
                "status_revisao",
                "categorias_detectadas",
                "palavras_chave_encontradas",
                "valor_pedidos",
                "total_pedidos",
            ]
            if column in filtered_df.columns
        ]
        st.dataframe(filtered_df[preview_columns], use_container_width=True)
        st.download_button(
            label="Baixar base categorizada",
            data=to_csv_bytes(filtered_df),
            file_name="categorized_output.csv",
            mime="text/csv",
        )

        st.markdown("#### Exportações prontas")
        export_columns = st.columns(3)
        export_columns[0].download_button(
            label="Base completa",
            data=to_csv_bytes(df),
            file_name="base_categorizada_completa.csv",
            mime="text/csv",
        )
        export_columns[1].download_button(
            label="Eventos de interesse",
            data=to_csv_bytes(interest_events),
            file_name="eventos_de_interesse_completo.csv",
            mime="text/csv",
        )
        export_columns[2].download_button(
            label="Eventos com dúvidas",
            data=to_csv_bytes(doubt_events),
            file_name="eventos_com_duvidas_completo.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
