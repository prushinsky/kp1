import streamlit as st
import pandas as pd
import json
import tempfile
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from utils.data_processor import DataProcessor
from utils.llm_analyzer import LLMAnalyzer

st.set_page_config(
    page_title="Анализ условий КП",
    page_icon="📊",
    layout="wide"
)

def initialize_session_state():
    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'analysis_result' not in st.session_state:
        st.session_state.analysis_result = None
    if 'proposals' not in st.session_state:
        st.session_state.proposals = None
    if 'stats' not in st.session_state:
        st.session_state.stats = None

def normalize_criteria_weights(weight_price: float, weight_delivery: float, weight_reliability: float) -> dict:
    total = weight_price + weight_delivery + weight_reliability
    if total <= 0:
        third = 1.0 / 3.0
        return {"weight_price": third, "weight_delivery": third, "weight_reliability": third}
    return {
        "weight_price": weight_price / total,
        "weight_delivery": weight_delivery / total,
        "weight_reliability": weight_reliability / total,
    }


def get_openrouter_api_key():
    api_key = None
    secret_key = None
    
    try:
        secret_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception:
        pass
    
    env_key = os.environ.get("OPENROUTER_API_KEY", "")
    
    if secret_key:
        api_key = secret_key
        if env_key != secret_key:
            os.environ["OPENROUTER_API_KEY"] = secret_key
    elif env_key:
        api_key = env_key
    
    return api_key if api_key else None

def main():
    st.title("📊 Анализ условий КП")
    st.markdown("Загрузите Excel файл с коммерческими предложениями (КП) для анализа и выбора лучшего варианта")
    
    initialize_session_state()
    
    with st.sidebar:
        st.header("Настройки анализа")
        st.markdown("---")
        
        st.subheader("Критерии оценки")
        weight_price = st.slider("Вес цены", 0.0, 1.0, 0.4, 0.05)
        weight_delivery = st.slider("Вес условий поставки", 0.0, 1.0, 0.3, 0.05)
        weight_reliability = st.slider("Вес надежности", 0.0, 1.0, 0.3, 0.05)
        
        use_llm = st.checkbox("Использовать LLM анализ (OpenRouter)", value=True)
        
        if use_llm:
            api_key = get_openrouter_api_key()
            if api_key:
                st.success("✅ API ключ OpenRouter настроен")
                st.info("LLM анализ использует OpenRouter API для комплексной оценки")
            else:
                st.error("❌ API ключ OpenRouter не найден")
                st.warning("Для использования LLM анализа добавьте ключ в .streamlit/secrets.toml или переменную окружения OPENROUTER_API_KEY")
        else:
            st.info("Будет использован простой анализ по минимальной цене")
        
        st.markdown("---")
        st.caption("Требуемые колонки в Excel:")
        st.caption("- Контрагент")
        st.caption("- товар")
        st.caption("- цена")
        st.caption("- скидка")
        st.caption("- условия поставки")
    
    uploaded_file = st.file_uploader(
        "Загрузите Excel файл с коммерческими предложениями",
        type=['xlsx', 'xls'],
        help="Файл должен содержать необходимые колонки"
    )
    
    if uploaded_file is not None:
        tmp_path = None
        try:
            suffix = Path(uploaded_file.name).suffix.lower() or ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name

            processor = DataProcessor()
            df, load_error = processor.load_excel_file(tmp_path)

            if load_error:
                st.error(load_error)
            elif df is not None:
                st.session_state.df = df
                st.session_state.proposals = processor.prepare_analysis_data(df)
                st.session_state.stats = processor.get_summary_statistics(df)

                st.success(f"Файл успешно загружен! Загружено {len(df)} предложений")
                
                with st.expander("📋 Просмотр данных", expanded=True):
                    st.dataframe(df, use_container_width=True)
                
                with st.expander("📊 Статистика", expanded=False):
                    stats = st.session_state.stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Всего предложений", stats['total_proposals'])
                        st.metric("Уникальных контрагентов", stats['unique_contractors'])
                    with col2:
                        st.metric("Средняя цена", f"{stats['avg_price']:.2f}")
                        st.metric("Средняя скидка", f"{stats['avg_discount']:.2f}%")
                    with col3:
                        if 'avg_price_with_discount' in stats:
                            st.metric("Средняя цена со скидкой", f"{stats['avg_price_with_discount']:.2f}")
                        st.metric("Минимальная цена", f"{stats['min_price']:.2f}")
                
                st.markdown("---")
                st.subheader("🔍 Анализ предложений")
                
                api_key = get_openrouter_api_key()
                
                if use_llm and not api_key:
                    st.error("❌ LLM анализ недоступен: API ключ не найден")
                    st.info("Используйте простой анализ или настройте API ключ в .streamlit/secrets.toml")
                
                if st.button("🚀 Запустить анализ", type="primary", use_container_width=True, disabled=(use_llm and not api_key)):
                    with st.spinner("Выполняется анализ..."):
                        if use_llm and api_key:
                            analyzer = LLMAnalyzer(api_key=api_key)
                            criteria = normalize_criteria_weights(
                                weight_price, weight_delivery, weight_reliability
                            )
                            result = analyzer.analyze_proposals(st.session_state.proposals, criteria)
                        else:
                            analyzer = LLMAnalyzer()
                            result = analyzer.simple_analysis(st.session_state.proposals)
                        
                        st.session_state.analysis_result = result
                
                if st.session_state.analysis_result:
                    display_analysis_results(st.session_state.analysis_result)
            
        except Exception as e:
            st.error(f"Ошибка при обработке файла: {str(e)}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    else:
        st.info("👈 Загрузите Excel файл для начала анализа")
        
        with st.expander("📝 Пример структуры файла", expanded=False):
            example_data = {
                'Контрагент': ['ООО "Поставщик 1"', 'АО "Компания 2"', 'ИП Иванов'],
                'товар': ['Ноутбук Dell XPS', 'Монитор Samsung', 'Клавиатура Logitech'],
                'цена': [120000, 35000, 4500],
                'скидка': [5, 10, 15],
                'условия поставки': ['Доставка 5 дней, самовывоз', 'Доставка 3 дня, бесплатно', 'Доставка 7 дней, предоплата']
            }
            example_df = pd.DataFrame(example_data)
            st.dataframe(example_df, use_container_width=True)
            st.caption("Скачайте шаблон для заполнения:")
            csv = example_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Скачать шаблон CSV",
                data=csv,
                file_name="шаблон_коммерческих_предложений.csv",
                mime="text/csv"
            )

def display_analysis_results(result):
    st.markdown("---")
    st.header("📋 Результаты анализа")
    
    if "error" in result:
        st.error(f"Ошибка анализа: {result['error']}")
        return
    
    if "best_by_price" in result:
        display_simple_analysis(result)
    else:
        display_llm_analysis(result)

def display_simple_analysis(result):
    st.subheader("📊 Простой анализ")
    
    def safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '.').replace('%', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return default
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("🏆 Лучшее по цене")
        best_price = result["best_by_price"]
        st.metric("Контрагент", best_price["контрагент"])
        price_with_discount = safe_float(best_price['цена_со_скидкой'])
        st.metric("Цена со скидкой", f"{price_with_discount:.2f}")
        st.caption(best_price["reason"])
    
    with col2:
        st.info("🎯 Лучшее по скидке")
        best_discount = result["best_by_discount"]
        st.metric("Контрагент", best_discount["контрагент"])
        discount = safe_float(best_discount['скидка'])
        st.metric("Скидка", f"{discount:.1f}%")
        st.caption(best_discount["reason"])
    
    st.metric("Всего проанализировано предложений", result["total_proposals"])

def display_llm_analysis(result):
    st.subheader("🏆 Лучшее коммерческое предложение")
    
    best = result.get("best_proposal_details", {})
    
    def safe_float(value, default=0.0):
        if value is None:
            return default
        try:
            if isinstance(value, str):
                value = value.replace(',', '.').replace('%', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return default
    
    price = safe_float(best.get('цена'))
    discount = safe_float(best.get('скидка'))
    price_with_discount = safe_float(best.get('цена_со_скидкой'))
    
    cols = st.columns([2, 1])
    with cols[0]:
        st.success(f"**Контрагент:** {best.get('контрагент', 'Не указано')}")
        st.write(f"**Товар:** {best.get('товар', 'Не указано')}")
        st.write(f"**Цена:** {price:.2f}")
        st.write(f"**Скидка:** {discount:.1f}%")
        st.write(f"**Цена со скидкой:** {price_with_discount:.2f}")
        st.write(f"**Условия поставки:** {best.get('условия_поставки', 'Не указано')}")
    
    with cols[1]:
        st.metric("ID предложения", result.get("best_proposal_id", "N/A"))
        st.metric("Итоговая цена", f"{price_with_discount:.2f}")
    
    st.markdown("---")
    st.subheader("📝 Объяснение выбора")
    st.write(result.get("explanation", "Объяснение не предоставлено"))
    
    analysis = result.get("analysis", {})
    if analysis:
        st.markdown("---")
        st.subheader("📈 Детальный анализ")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if "strengths" in analysis:
                st.info("✅ Сильные стороны")
                for strength in analysis["strengths"]:
                    st.write(f"• {strength}")
        
        with col2:
            if "weaknesses" in analysis:
                st.warning("⚠️ Слабые стороны / Риски")
                for weakness in analysis["weaknesses"]:
                    st.write(f"• {weakness}")
        
        if "recommendations" in analysis:
            st.success("💡 Рекомендации")
            for rec in analysis["recommendations"]:
                st.write(f"• {rec}")
    
    if "alternative_proposals" in result and result["alternative_proposals"]:
        st.markdown("---")
        st.subheader("🔄 Альтернативные варианты")
        for alt in result["alternative_proposals"]:
            with st.expander(f"Альтернатива #{alt.get('id', 'N/A')}"):
                st.write(alt.get("reason", "Причина не указана"))
    
    st.markdown("---")
    st.subheader("📥 Экспорт результатов")
    
    col1, col2 = st.columns(2)
    with col1:
        json_str = json.dumps(result, ensure_ascii=False, indent=2)
        st.download_button(
            label="📄 Скачать JSON отчет",
            data=json_str,
            file_name="анализ_коммерческих_предложений.json",
            mime="application/json"
        )
    
    with col2:
        if st.session_state.df is not None and "best_proposal_id" in result:
            best_id = result["best_proposal_id"]
            best_row = st.session_state.df.iloc[best_id - 1] if best_id > 0 else None
            if best_row is not None:
                csv = best_row.to_frame().T.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📊 Скачать лучшее предложение (CSV)",
                    data=csv,
                    file_name="лучшее_предложение.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()