import logging
import os
import tempfile
import html
from io import BytesIO
from pathlib import Path
from typing import Dict, Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from config.config import Config
from utils.data_processor import DataProcessor
from utils.llm_analyzer import LLMAnalyzer

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}
MAX_TELEGRAM_MESSAGE_LENGTH = 4000
PDF_FONT_NAME = "ReportFont"
PDF_FALLBACK_FONT = "Helvetica"


def normalize_criteria_weights(weight_price: float, weight_delivery: float, weight_reliability: float) -> Dict[str, float]:
    total = weight_price + weight_delivery + weight_reliability
    if total <= 0:
        third = 1.0 / 3.0
        return {"weight_price": third, "weight_delivery": third, "weight_reliability": third}
    return {
        "weight_price": weight_price / total,
        "weight_delivery": weight_delivery / total,
        "weight_reliability": weight_reliability / total,
    }


def trim_message(text: str) -> str:
    if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return text
    return text[: MAX_TELEGRAM_MESSAGE_LENGTH - 30] + "\n\n... (сообщение сокращено)"


def get_user_name(update: Update) -> str:
    if update.effective_user and update.effective_user.first_name:
        return update.effective_user.first_name
    return "коллега"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", ".").replace("%", "").strip()
        return float(value)
    except (ValueError, TypeError):
        return default


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _register_pdf_font() -> str:
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, path))
                return PDF_FONT_NAME
            except Exception:
                logger.debug("Failed to register font %s", path, exc_info=True)
    return PDF_FALLBACK_FONT


def format_analysis_markdown(result: Dict[str, Any], rows_count: int, used_llm: bool, user_name: str) -> str:
    cfg = Config()
    provider_name = "Ollama (local)" if cfg.LLM_PROVIDER == "ollama" else "OpenRouter"
    mode_text = f"LLM ({provider_name})" if used_llm else "Простой анализ"
    lines = [
        "# Отчет по анализу коммерческих предложений",
        "",
        f"**Пользователь:** {user_name}",
        f"**Обработано строк:** {rows_count}",
        f"**Режим:** {mode_text}",
        "",
    ]

    if "error" in result:
        lines.extend(["## Ошибка", "", str(result["error"])])
        return "\n".join(lines)

    if "best_by_price" in result:
        best_price = result.get("best_by_price", {})
        best_discount = result.get("best_by_discount", {})
        lines.extend(
            [
                "## Итог (простой анализ)",
                "",
                "### Лучшее по цене",
                f"- Контрагент: {best_price.get('контрагент', 'Не указано')}",
                f"- Цена со скидкой: {safe_float(best_price.get('цена_со_скидкой')):,.2f}",
                "",
                "### Лучшее по скидке",
                f"- Контрагент: {best_discount.get('контрагент', 'Не указано')}",
                f"- Скидка: {safe_float(best_discount.get('скидка')):.1f}%",
            ]
        )
        return "\n".join(lines)

    best = result.get("best_proposal_details", {})
    analysis = result.get("analysis", {})
    lines.extend(
        [
            "## Лучшее предложение",
            f"- ID: {result.get('best_proposal_id', 'N/A')}",
            f"- Контрагент: {best.get('контрагент', 'Не указано')}",
            f"- Товар: {best.get('товар', 'Не указано')}",
            f"- Цена: {safe_float(best.get('цена')):,.2f}",
            f"- Скидка: {safe_float(best.get('скидка')):.1f}%",
            f"- Цена со скидкой: {safe_float(best.get('цена_со_скидкой')):,.2f}",
            "",
            "## Почему выбрано",
            str(result.get("explanation", "Объяснение не предоставлено")),
        ]
    )

    strengths = analysis.get("strengths", [])
    weaknesses = analysis.get("weaknesses", [])
    recommendations = analysis.get("recommendations", [])
    if strengths:
        lines.extend(["", "## Сильные стороны"] + [f"- {item}" for item in strengths[:5]])
    if weaknesses:
        lines.extend(["", "## Риски"] + [f"- {item}" for item in weaknesses[:5]])
    if recommendations:
        lines.extend(["", "## Рекомендации"] + [f"- {item}" for item in recommendations[:5]])

    return "\n".join(lines)


def markdown_to_pdf_buffer(markdown_text: str) -> BytesIO:
    font_name = _register_pdf_font()
    font_size = 10
    line_height = 14
    margin_x = 40
    margin_y = 40
    max_width = A4[0] - (2 * margin_x)
    y = A4[1] - margin_y

    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.setTitle("Анализ коммерческих предложений")
    c.setFont(font_name, font_size)

    for raw_line in markdown_text.splitlines():
        line = raw_line if raw_line.strip() else " "
        wrapped = simpleSplit(line, font_name, font_size, max_width)
        for piece in wrapped:
            if y <= margin_y:
                c.showPage()
                c.setFont(font_name, font_size)
                y = A4[1] - margin_y
            c.drawString(margin_x, y, piece)
            y -= line_height
        if not raw_line.strip():
            y -= 2

    c.save()
    pdf_buffer.seek(0)
    pdf_buffer.name = "analysis_report.pdf"
    return pdf_buffer


def format_status_message(percent: int, title: str, details: str = "") -> str:
    base = (
        f"⏳ <b>Обработка документа: {percent}%</b>\n"
        "──────────────────\n"
        f"{esc(title)}"
    )
    if details:
        base += f"\n{esc(details)}"
    return base


async def update_status(status_message, percent: int, title: str, details: str = "") -> None:
    try:
        await status_message.edit_text(
            format_status_message(percent, title, details),
            parse_mode="HTML",
        )
    except Exception:
        # If Telegram rejects message editing for any reason, continue processing silently.
        logger.debug("Failed to update status message", exc_info=True)


def format_analysis_message(result: Dict[str, Any], rows_count: int, used_llm: bool) -> str:
    if "error" in result:
        return (
            "❌ <b>Ошибка анализа</b>\n"
            "──────────────────\n"
            f"{esc(result['error'])}"
        )

    cfg = Config()
    provider_name = "Ollama (local)" if cfg.LLM_PROVIDER == "ollama" else "OpenRouter"
    mode_text = f"LLM ({provider_name})" if used_llm else "Простой анализ"
    header = (
        "✅ <b>Анализ завершен</b>\n"
        "──────────────────\n"
        f"📄 <b>Обработано строк:</b> {rows_count}\n"
        f"🧠 <b>Режим:</b> {esc(mode_text)}\n\n"
    )

    if "best_by_price" in result:
        best_price = result["best_by_price"]
        best_discount = result["best_by_discount"]
        best_price_value = safe_float(best_price.get("цена_со_скидкой"))
        best_discount_value = safe_float(best_discount.get("скидка"))
        body = (
            "🏆 <b>Лучшее по цене</b>\n"
            f"• <b>Контрагент:</b> {esc(best_price.get('контрагент', 'Не указано'))}\n"
            f"• <b>Цена со скидкой:</b> {best_price_value:,.2f}\n\n"
            "🎯 <b>Лучшее по скидке</b>\n"
            f"• <b>Контрагент:</b> {esc(best_discount.get('контрагент', 'Не указано'))}\n"
            f"• <b>Скидка:</b> {best_discount_value:.1f}%\n"
        )
        return trim_message(header + body)

    best = result.get("best_proposal_details", {})
    analysis = result.get("analysis", {})
    strengths = analysis.get("strengths", [])
    weaknesses = analysis.get("weaknesses", [])

    body = (
        "🏆 <b>Лучшее предложение</b>\n"
        f"• <b>ID:</b> {esc(result.get('best_proposal_id', 'N/A'))}\n"
        f"• <b>Контрагент:</b> {esc(best.get('контрагент', 'Не указано'))}\n"
        f"• <b>Товар:</b> {esc(best.get('товар', 'Не указано'))}\n"
        f"• <b>Цена:</b> {safe_float(best.get('цена')):,.2f}\n"
        f"• <b>Скидка:</b> {safe_float(best.get('скидка')):.1f}%\n"
        f"• <b>Цена со скидкой:</b> {safe_float(best.get('цена_со_скидкой')):,.2f}\n\n"
        "📝 <b>Почему выбрано</b>\n"
        f"{esc(result.get('explanation', 'Объяснение не предоставлено'))}\n\n"
    )

    if strengths:
        body += "✅ <b>Сильные стороны</b>\n" + "\n".join([f"• {esc(item)}" for item in strengths[:3]]) + "\n\n"
    if weaknesses:
        body += "⚠️ <b>Риски</b>\n" + "\n".join([f"• {esc(item)}" for item in weaknesses[:3]]) + "\n"

    return trim_message(header + body)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    user_name = get_user_name(update)
    await update.message.reply_text(
        f"Привет, <b>{esc(user_name)}</b>! 👋\n\n"
        "Я помогу сравнить коммерческие предложения из Excel.\n"
        "Отправьте файл `.xlsx/.xls/.xlsm`, и я пришлю:\n"
        "• краткий красивый итог в чате;\n"
        "• JSON-отчет с деталями анализа.",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await update.message.reply_text(
        "📌 <b>Команды</b>\n"
        "/start — приветствие и инструкция\n"
        "/help — эта справка\n\n"
        "📎 <b>Поддерживаемые файлы:</b> .xlsx, .xls, .xlsm\n"
        "🧾 <b>Обязательные колонки:</b>\n"
        "Контрагент, товар, цена, скидка, условия поставки.",
        parse_mode="HTML",
    )


async def handle_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    if not update.message:
        return

    # Respond with guidance for plain direct messages in private chat.
    if not update.effective_chat or update.effective_chat.type != "private":
        return

    user_name = get_user_name(update)
    await update.message.reply_text(
        f"<b>{esc(user_name)}</b>, я анализирую коммерческие предложения из Excel.\n\n"
        "<b>Как я работаю:</b>\n"
        "1) Вы отправляете файл <code>.xlsx/.xls/.xlsm</code>.\n"
        "2) Я проверяю структуру и обязательные колонки.\n"
        "3) Выполняю анализ (LLM через OpenRouter или простой режим).\n"
        "4) Отправляю красивый итог и JSON-отчет.\n\n"
        "<b>Обязательные колонки:</b>\n"
        "Контрагент, товар, цена, скидка, условия поставки.\n\n"
        "Просто отправьте Excel-файл, и я начну.",
        parse_mode="HTML",
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    if not update.message or not update.message.document:
        return

    document = update.message.document
    file_name = document.file_name or "proposals.xlsx"
    suffix = Path(file_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        await update.message.reply_text("Поддерживаются только файлы .xlsx, .xls, .xlsm.")
        return

    cfg = Config()
    user_name = get_user_name(update)
    status_message = await update.message.reply_text(
        format_status_message(5, f"{user_name}, файл получен.", "Готовлю обработку..."),
        parse_mode="HTML",
    )

    tmp_path = None
    try:
        await update_status(status_message, 20, "Скачиваю файл из Telegram...")
        tg_file = await document.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_path = tmp_file.name
            await tg_file.download_to_drive(custom_path=tmp_path)

        await update_status(status_message, 40, "Читаю Excel и проверяю колонки...")
        processor = DataProcessor()
        df, load_error = processor.load_excel_file(tmp_path)
        if load_error:
            await status_message.edit_text(
                "❌ <b>Ошибка чтения Excel</b>\n"
                "──────────────────\n"
                f"{esc(load_error)}",
                parse_mode="HTML",
            )
            await update.message.reply_text(f"Ошибка чтения Excel: {load_error}")
            return

        await update_status(status_message, 60, "Подготавливаю данные для анализа...")
        proposals = processor.prepare_analysis_data(df)
        provider = (cfg.LLM_PROVIDER or "openrouter").strip().lower()
        provider_ready = provider == "ollama" or bool((cfg.OPENROUTER_API_KEY or "").strip())
        used_llm = cfg.TELEGRAM_USE_LLM and provider_ready
        provider_name = "Ollama (local)" if provider == "ollama" else "OpenRouter"
        analysis_mode = f"LLM ({provider_name})" if used_llm else "Простой анализ"
        await update_status(status_message, 80, "Выполняю анализ предложений...", f"Режим: {analysis_mode}")
        if used_llm:
            criteria = normalize_criteria_weights(
                cfg.TELEGRAM_WEIGHT_PRICE,
                cfg.TELEGRAM_WEIGHT_DELIVERY,
                cfg.TELEGRAM_WEIGHT_RELIABILITY,
            )
            analyzer = LLMAnalyzer(
                provider=provider,
                api_key=cfg.OPENROUTER_API_KEY if provider == "openrouter" else "ollama",
                base_url=cfg.OPENROUTER_BASE_URL if provider == "openrouter" else cfg.OLLAMA_BASE_URL,
                model=cfg.OPENROUTER_MODEL if provider == "openrouter" else cfg.OLLAMA_MODEL,
            )
            result = analyzer.analyze_proposals(proposals, criteria)
        else:
            analyzer = LLMAnalyzer()
            result = analyzer.simple_analysis(proposals)

        await update_status(status_message, 90, "Формирую ответ и отчет...")
        message = f"<b>{esc(user_name)}</b>, ваш результат готов:\n\n" + format_analysis_message(result, len(df), used_llm)
        await update.message.reply_text(message, parse_mode="HTML")

        report_markdown = format_analysis_markdown(result, len(df), used_llm, user_name)
        report_file = markdown_to_pdf_buffer(report_markdown)
        await update.message.reply_document(document=report_file, caption="PDF-отчет анализа")
        await status_message.edit_text(
            "✅ <b>Обработка завершена: 100%</b>\n"
            "──────────────────\n"
            f"Готово, {esc(user_name)}. Результат и PDF-отчет отправлены.",
            parse_mode="HTML",
        )

    except Exception as exc:
        logger.exception("Telegram bot processing error")
        await status_message.edit_text(
            "❌ <b>Ошибка обработки документа</b>\n"
            "──────────────────\n"
            f"{esc(exc)}",
            parse_mode="HTML",
        )
        await update.message.reply_text(f"Ошибка обработки файла: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main() -> None:
    cfg = Config()
    if not cfg.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в .env")

    application = Application.builder().token(cfg.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_message))

    logger.info("Telegram bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
