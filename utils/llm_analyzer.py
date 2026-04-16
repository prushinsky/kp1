import json
import logging
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional
from openai import OpenAI
from config.config import Config

logger = logging.getLogger(__name__)

class LLMAnalyzer:
    def __init__(self, api_key=None, base_url=None, model=None, max_tokens=None, temperature=None):
        self.config = Config()
        self.api_key = api_key or self.config.OPENROUTER_API_KEY
        self.base_url = base_url or self.config.OPENROUTER_BASE_URL
        self.model = model or self.config.OPENROUTER_MODEL
        self.max_tokens = max_tokens or self.config.MAX_TOKENS
        self.temperature = temperature or self.config.TEMPERATURE
        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    @staticmethod
    def _is_openrouter_base_url(base_url: str) -> bool:
        if not base_url:
            return False
        parsed = urlparse(base_url)
        host = (parsed.netloc or "").lower()
        return host == "openrouter.ai" or host.endswith(".openrouter.ai")
    
    def analyze_proposals(self, proposals: List[Dict[str, Any]], criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not proposals:
            return {"error": "No proposals provided"}

        if not (self.api_key or "").strip():
            return {"error": "Для LLM-анализа нужен API-ключ OpenRouter."}

        if not self._is_openrouter_base_url(self.base_url):
            return {
                "error": (
                    "LLM-анализ разрешен только через OpenRouter API. "
                    "Проверьте OPENROUTER_BASE_URL (ожидается https://openrouter.ai/api/v1)."
                )
            }

        system_prompt = self._create_system_prompt(criteria)
        user_prompt = self._create_user_prompt(proposals, criteria)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            result = self._convert_strings_to_floats(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            return {"error": f"LLM analysis failed: {str(e)}"}
    
    def _convert_strings_to_floats(self, obj):
        if isinstance(obj, dict):
            new_dict = {}
            for key, value in obj.items():
                if key in ['цена', 'скидка', 'цена_со_скидкой']:
                    try:
                        if isinstance(value, str):
                            value = value.replace(',', '.').replace('%', '').strip()
                        new_dict[key] = float(value) if value not in [None, ''] else 0.0
                    except (ValueError, TypeError):
                        new_dict[key] = 0.0
                elif key in ['id', 'best_proposal_id']:
                    try:
                        if isinstance(value, str):
                            value = value.strip()
                        new_dict[key] = int(float(value)) if value not in [None, ''] else 0
                    except (ValueError, TypeError):
                        new_dict[key] = 0
                else:
                    new_dict[key] = self._convert_strings_to_floats(value)
            return new_dict
        elif isinstance(obj, list):
            return [self._convert_strings_to_floats(item) for item in obj]
        else:
            return obj
    
    def _create_system_prompt(self, criteria: Optional[Dict[str, Any]] = None) -> str:
        criteria_note = ""
        if criteria:
            criteria_note = (
                "\nПользователь задал относительные веса критериев (сумма = 1): "
                f"цена — {criteria.get('weight_price', 0):.3f}, "
                f"условия поставки — {criteria.get('weight_delivery', 0):.3f}, "
                f"прочие факторы по полям данных (название контрагента и товара без внешних знаний) — "
                f"{criteria.get('weight_reliability', 0):.3f}. "
                "Учитывай эти доли при сравнении предложений.\n"
            )

        return f"""Ты эксперт по анализу коммерческих предложений.
Твоя задача — проанализировать список коммерческих предложений и выбрать лучшее на основе данных из таблицы.
{criteria_note}
Доступные данные по каждому предложению только такие: контрагент, товар, цена, скидка, цена со скидкой, условия поставки.
Не выдумывай репутацию, сертификаты, историю компаний или качество товара, если этого нет в тексте условий или названиях.
Критерии оценки строго из данных:
1. Цена с учётом скидки — чем ниже, тем лучше (если сопоставимо по условиям).
2. Условия поставки — только то, что явно указано в поле условий (сроки, оплата, доставка и т.д.).
3. Поверхностная оценка по формулировкам названия контрагента и товара — только как слабый сигнал, без домыслов о «надёжности рынка».

Ты должен вернуть ответ в формате JSON со следующей структурой:
{{
    "best_proposal_id": <id лучшего предложения>,
    "best_proposal_details": {{
        "контрагент": "...",
        "товар": "...",
        "цена": "...",
        "скидка": "...",
        "цена_со_скидкой": "...",
        "условия_поставки": "..."
    }},
    "analysis": {{
        "criteria_used": ["цена", "условия поставки", ...],
        "strengths": ["сильные стороны выбранного предложения"],
        "weaknesses": ["слабые стороны или риски"],
        "recommendations": ["рекомендации по работе с выбранным контрагентом"]
    }},
    "explanation": "Подробное объяснение, почему выбрано именно это предложение",
    "alternative_proposals": [
        {{
            "id": <id альтернативы>,
            "reason": "почему это хорошая альтернатива"
        }}
    ]
}}

Будь объективным и обоснуй свой выбор конкретными фактами из данных."""
    
    def _create_user_prompt(self, proposals: List[Dict[str, Any]], criteria: Optional[Dict[str, Any]]) -> str:
        def safe_format_number(value, fmt='.2f'):
            try:
                if isinstance(value, str):
                    value = value.replace(',', '.').replace('%', '').strip()
                num = float(value)
                return format(num, fmt)
            except (ValueError, TypeError):
                return '0.00' if fmt == '.2f' else '0.0'
        
        prompt = "Проанализируй следующие коммерческие предложения и выбери лучшее:\n\n"
        
        for prop in proposals:
            prompt += f"Предложение #{prop['id']}:\n"
            prompt += f"  Контрагент: {prop['контрагент']}\n"
            prompt += f"  Товар: {prop['товар']}\n"
            prompt += f"  Цена: {safe_format_number(prop['цена'], '.2f')}\n"
            prompt += f"  Скидка: {safe_format_number(prop['скидка'], '.1f')}%\n"
            prompt += f"  Цена со скидкой: {safe_format_number(prop['цена_со_скидкой'], '.2f')}\n"
            prompt += f"  Условия поставки: {prop['условия_поставки']}\n"
            prompt += "\n"
        
        if criteria:
            prompt += f"\nДополнительные критерии оценки: {json.dumps(criteria, ensure_ascii=False)}\n"
        
        prompt += "\nВерни результат анализа в указанном JSON формате."
        
        return prompt
    
    def simple_analysis(self, proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not proposals:
            return {"error": "No proposals provided"}
        
        try:
            min_price_proposal = min(proposals, key=lambda x: x['цена_со_скидкой'])
            max_discount_proposal = max(proposals, key=lambda x: x['скидка'])
            
            return {
                "best_by_price": {
                    "id": min_price_proposal['id'],
                    "контрагент": min_price_proposal['контрагент'],
                    "цена_со_скидкой": min_price_proposal['цена_со_скидкой'],
                    "reason": "Самая низкая цена с учетом скидки"
                },
                "best_by_discount": {
                    "id": max_discount_proposal['id'],
                    "контрагент": max_discount_proposal['контрагент'],
                    "скидка": max_discount_proposal['скидка'],
                    "reason": "Самая высокая скидка"
                },
                "total_proposals": len(proposals)
            }
        except Exception as e:
            logger.error(f"Error in simple analysis: {e}")
            return {"error": f"Simple analysis failed: {str(e)}"}