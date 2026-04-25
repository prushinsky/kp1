import sys
sys.path.append('.')

from utils.data_processor import DataProcessor
from utils.llm_analyzer import LLMAnalyzer

def test_data_loading():
    print("Тестирование загрузки данных...")
    processor = DataProcessor()
    df, load_error = processor.load_excel_file("data/test_proposals.xlsx")

    if load_error:
        print(f"❌ Ошибка загрузки: {load_error}")
        return None

    if df is not None:
        print(f"✅ Данные загружены успешно. Строк: {len(df)}")
        print("\nПервые 3 строки:")
        print(df[['Контрагент', 'товар', 'цена', 'скидка']].head(3))
        
        proposals = processor.prepare_analysis_data(df)
        print(f"\n✅ Подготовлено предложений: {len(proposals)}")
        print("\nПервое предложение:")
        print(proposals[0])
        
        stats = processor.get_summary_statistics(df)
        print("\n✅ Статистика:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        return proposals
    else:
        print("❌ Ошибка загрузки данных")
        return None

def test_simple_analysis(proposals):
    print("\n\nТестирование простого анализа...")
    analyzer = LLMAnalyzer()
    result = analyzer.simple_analysis(proposals)
    
    if "error" not in result:
        print("✅ Простой анализ выполнен успешно")
        print(f"Лучшее по цене: {result['best_by_price']['контрагент']} (цена со скидкой: {result['best_by_price']['цена_со_скидкой']:.2f})")
        print(f"Лучшее по скидке: {result['best_by_discount']['контрагент']} (скидка: {result['best_by_discount']['скидка']:.1f}%)")
    else:
        print(f"❌ Ошибка простого анализа: {result['error']}")
    
    return result

def test_llm_analysis(proposals):
    print("\n\nТестирование LLM анализа (требуется API ключ)...")
    analyzer = LLMAnalyzer()

    provider = (analyzer.config.LLM_PROVIDER or "openrouter").strip().lower()
    if provider == "openrouter" and (
        not analyzer.config.OPENROUTER_API_KEY or analyzer.config.OPENROUTER_API_KEY == "your_api_key_here"
    ):
        print("⚠️ API ключ OpenRouter не установлен. Пропускаем LLM анализ.")
        print("Установите OPENROUTER_API_KEY в .env или переключитесь на LLM_PROVIDER=ollama")
        return None
    
    result = analyzer.analyze_proposals(proposals[:3])  # Тестируем на 3 предложениях
    
    if "error" not in result:
        print("✅ LLM анализ выполнен успешно")
        if "best_proposal_id" in result:
            print(f"Лучшее предложение ID: {result['best_proposal_id']}")
            if "explanation" in result:
                print(f"Объяснение: {result['explanation'][:200]}...")
    else:
        print(f"❌ Ошибка LLM анализа: {result['error']}")
    
    return result

if __name__ == "__main__":
    print("=" * 60)
    print("Тестирование анализатора коммерческих предложений")
    print("=" * 60)
    
    proposals = test_data_loading()
    
    if proposals:
        test_simple_analysis(proposals)
        test_llm_analysis(proposals)
    
    print("\n" + "=" * 60)
    print("Тестирование завершено")
    print("=" * 60)